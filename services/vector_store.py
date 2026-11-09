import logging
import threading
from collections import OrderedDict
from typing import Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_huggingface import HuggingFaceEmbeddings

from core.config import get_settings
from services.bm25 import BM25Index

logger = logging.getLogger(__name__)

_BM25_CACHE_SCOPES = 32


class VectorStoreManager:
    def __init__(self):
        self._store: Optional[Chroma] = None
        self._lock = threading.Lock()
        self._bm25_cache: OrderedDict = OrderedDict()
        self._bm25_lock = threading.Lock()

    def _ensure_initialized(self) -> None:
        if self._store is not None:
            return
        with self._lock:
            if self._store is not None:
                return
            settings = get_settings()
            embeddings = HuggingFaceEmbeddings(
                model_name=settings.EMBEDDING_MODEL,
                model_kwargs={"device": settings.EMBEDDING_DEVICE},
                encode_kwargs={"normalize_embeddings": True},
            )
            if settings.CHROMA_HOST:
                # Server mode: safe for several API replicas + the ingestion worker.
                import chromadb

                self._store = Chroma(
                    collection_name=settings.CHROMA_COLLECTION,
                    embedding_function=embeddings,
                    client=chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT),
                )
            else:
                # Embedded mode: single process only.
                self._store = Chroma(
                    collection_name=settings.CHROMA_COLLECTION,
                    embedding_function=embeddings,
                    persist_directory=settings.CHROMA_PERSIST_DIR,
                )

    def store_chunks(self, chunks: list[Document]) -> None:
        self._ensure_initialized()
        self._store.add_documents(chunks)
        logger.info(f"Stored {len(chunks)} chunks in vector store")

    @staticmethod
    def _where(doc_id: Optional[str], owner_id: Optional[str]) -> Optional[dict]:
        conditions = []
        if owner_id:
            conditions.append({"owner_id": owner_id})
        if doc_id:
            conditions.append({"doc_id": doc_id})
        if not conditions:
            return None
        return conditions[0] if len(conditions) == 1 else {"$and": conditions}

    def retrieve(
        self,
        query: str,
        k: int,
        doc_id: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> list[tuple[Document, float]]:
        """Semantic search. Returns (chunk, cosine similarity) pairs, best first.

        Each chunk's metadata carries `_chunk_id` so results can be fused with
        keyword hits.
        """
        self._ensure_initialized()
        query_embedding = self._store._embedding_function.embed_query(query)
        results = self._store._collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            where=self._where(doc_id, owner_id),
        )

        docs_with_scores = []
        if results and results.get("documents"):
            for i, chunk_id in enumerate(results["ids"][0]):
                metadata = dict(results["metadatas"][0][i]) if results.get("metadatas") else {}
                metadata["_chunk_id"] = chunk_id
                distance = results["distances"][0][i] if results.get("distances") else 0.0
                # Chroma returns cosine distance; convert to similarity.
                docs_with_scores.append(
                    (Document(page_content=results["documents"][0][i], metadata=metadata), 1 - distance)
                )

        logger.debug(f"Retrieved {len(docs_with_scores)} documents for query, doc_id={doc_id}")
        return docs_with_scores

    def keyword_search(
        self,
        query: str,
        k: int,
        doc_id: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> list[tuple[Document, float]]:
        """BM25 over the chunks in scope. Complements semantic search for exact
        terms (names, ids, acronyms) that embeddings blur.

        The index is built per (owner, doc) scope and cached; it is rebuilt
        whenever the set of chunk ids in that scope changes, which also covers
        writes made by another process (the ingestion worker).
        """
        self._ensure_initialized()
        settings = get_settings()
        where = self._where(doc_id, owner_id)
        collection = self._store._collection

        ids = collection.get(where=where, include=[])["ids"]
        if not ids:
            return []
        if len(ids) > settings.HYBRID_MAX_CHUNKS:
            logger.warning(
                f"Skipping keyword search: {len(ids)} chunks in scope exceeds HYBRID_MAX_CHUNKS"
            )
            return []

        scope = (owner_id, doc_id)
        signature = (len(ids), hash(tuple(sorted(ids))))
        with self._bm25_lock:
            cached = self._bm25_cache.get(scope)
            if cached is not None and cached[0] == signature:
                self._bm25_cache.move_to_end(scope)
                _, index, chunk_ids, texts, metas = cached
            else:
                data = collection.get(where=where, include=["documents", "metadatas"])
                chunk_ids, texts, metas = data["ids"], data["documents"], data["metadatas"]
                index = BM25Index(texts)
                self._bm25_cache[scope] = (signature, index, chunk_ids, texts, metas)
                while len(self._bm25_cache) > _BM25_CACHE_SCOPES:
                    self._bm25_cache.popitem(last=False)

        hits = []
        for i, score in index.top_k(query, k):
            metadata = dict(metas[i] or {})
            metadata["_chunk_id"] = chunk_ids[i]
            hits.append((Document(page_content=texts[i], metadata=metadata), score))
        return hits

    def delete_document(self, doc_id: str) -> None:
        self._ensure_initialized()
        self._store._collection.delete(where={"doc_id": doc_id})
        logger.info(f"Deleted document {doc_id} from vector store")

    def as_retriever(self, doc_id: Optional[str] = None, k: int = 5) -> BaseRetriever:
        self._ensure_initialized()
        search_kwargs: dict = {"k": k}
        if doc_id:
            search_kwargs["filter"] = {"doc_id": doc_id}
        return self._store.as_retriever(search_kwargs=search_kwargs)


vector_store_manager = VectorStoreManager()
