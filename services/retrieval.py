"""Retrieval pipeline: semantic + keyword search, rank fusion, rerank, threshold."""
import hashlib
import logging
from typing import Optional

from langchain_core.documents import Document

from core.config import get_settings
from services.reranker import reranker
from services.vector_store import vector_store_manager

logger = logging.getLogger(__name__)

_RRF_K = 60  # standard reciprocal-rank-fusion damping constant


def _key(doc: Document) -> str:
    cid = doc.metadata.get("_chunk_id")
    return cid or hashlib.sha1(doc.page_content.encode()).hexdigest()  # noqa: S324 - not security


def rrf_fuse(rankings: list[list[Document]]) -> list[Document]:
    """Reciprocal Rank Fusion: merges ranked lists using ranks only, so scores from
    different scorers (cosine vs BM25) never need to be put on one scale."""
    fused: dict[str, float] = {}
    docs: dict[str, Document] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking):
            key = _key(doc)
            docs.setdefault(key, doc)
            fused[key] = fused.get(key, 0.0) + 1.0 / (_RRF_K + rank + 1)
    return [docs[k] for k in sorted(fused, key=fused.get, reverse=True)]


def retrieve_chunks(
    query: str,
    k: int,
    doc_id: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> list[Document]:
    """Return up to k relevant chunks, each with metadata `_score` in [0, 1].

    An empty list means nothing in scope was relevant enough to answer from.
    """
    s = get_settings()
    candidates = max(s.RETRIEVAL_CANDIDATES, k)

    semantic = vector_store_manager.retrieve(query, k=candidates, doc_id=doc_id, owner_id=owner_id)
    similarity = {_key(d): score for d, score in semantic}
    rankings = [[d for d, _ in semantic]]

    if s.HYBRID_ENABLED:
        keyword = vector_store_manager.keyword_search(query, k=candidates, doc_id=doc_id, owner_id=owner_id)
        if keyword:
            rankings.append([d for d, _ in keyword])

    shortlist = rrf_fuse(rankings)[:candidates]
    if not shortlist:
        return []

    scores: Optional[list[float]] = None
    if s.RERANK_ENABLED:
        scores = reranker.score(query, [d.page_content for d in shortlist])

    if scores is not None:
        ranked = sorted(zip(shortlist, scores, strict=True), key=lambda x: x[1], reverse=True)
    else:
        # No reranker: keep fused order; score = cosine similarity where known.
        ranked = [(d, similarity.get(_key(d), 0.0)) for d in shortlist]

    kept = []
    for doc, score in ranked:
        # A keyword-only hit has no cosine score when the reranker is off; don't
        # discard it for lacking one.
        unscored = scores is None and _key(doc) not in similarity
        if score >= s.MIN_RELEVANCE_SCORE or unscored:
            doc.metadata["_score"] = score
            kept.append(doc)
        if len(kept) == k:
            break

    logger.info(
        f"Retrieval: {len(semantic)} semantic, {len(shortlist)} fused, {len(kept)} kept "
        f"(reranked={scores is not None})"
    )
    return kept
