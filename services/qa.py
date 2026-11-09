import asyncio
import logging
from functools import lru_cache
from typing import AsyncIterator, Optional
from uuid import UUID

from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import Runnable
from langchain_groq import ChatGroq

from api.schemas import AnswerResponse, SourceChunk
from core.config import get_settings
from core.observability import LLM_ERRORS, NO_ANSWER, UNVERIFIED_CITATIONS
from services.citations import find_unverified_citations
from services.retrieval import retrieve_chunks
from services.session_memory import session_memory

logger = logging.getLogger(__name__)

_CONDENSE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "Given the chat history and a follow-up question, rephrase the follow-up "
        "to be a standalone question. If there is no chat history, return the question as-is.",
    ),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])

_QA_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "Answer using ONLY the context below. "
        "Cite sources as [filename:page] when referencing specific content. "
        "If the context is insufficient, say so clearly.\n\n{context}",
    ),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])


class _ManagerRetriever(BaseRetriever):
    doc_id: Optional[str] = None
    owner_id: Optional[str] = None
    k: int = 5

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        logger.debug(f"Retrieving {self.k} documents for query: {query}, doc_id: {self.doc_id}")
        docs = retrieve_chunks(query, k=self.k, doc_id=self.doc_id, owner_id=self.owner_id)
        logger.info(f"Retrieved {len(docs)} relevant documents, doc_id={self.doc_id}")
        return docs


# ── shared helpers ───────────────────────────────────────────────────────────

NO_ANSWER_TEXT = (
    "I couldn't find anything relevant to that question in the documents available to me. "
    "Try rephrasing it, or upload a document that covers this topic."
)


def _build_llm(model: str, streaming: bool) -> ChatGroq:
    settings = get_settings()
    return ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model=model,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        streaming=streaming,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=settings.LLM_MAX_RETRIES,
    )


@lru_cache
def _get_llm(streaming: bool) -> Runnable:
    """One client per mode, built lazily on first use and reused across requests.

    Transient errors are retried by the client; if the primary model is still
    failing (rate limit, outage), the request falls back to a smaller model.
    """
    settings = get_settings()
    primary = _build_llm(settings.GROQ_CHAT_MODEL, streaming)
    fallback = settings.GROQ_FALLBACK_MODEL
    if fallback and fallback != settings.GROQ_CHAT_MODEL:
        return primary.with_fallbacks([_build_llm(fallback, streaming)])
    return primary


def _chat_history(session_id: UUID, owner_id: Optional[str]) -> list[BaseMessage]:
    turns = session_memory.get_turns(session_id, owner_id)
    return [
        msg
        for turn in turns
        for msg in (HumanMessage(content=turn["question"]), AIMessage(content=turn["answer"]))
    ]


def _make_retriever(doc_id: Optional[UUID], owner_id: Optional[str]) -> _ManagerRetriever:
    return _ManagerRetriever(
        doc_id=str(doc_id) if doc_id else None,
        owner_id=owner_id,
        k=get_settings().RETRIEVAL_K,
    )


def _format_context(docs: list[Document]) -> str:
    return "\n\n".join(
        f"[{doc.metadata.get('filename', '')}:{doc.metadata.get('page_number', '')}]\n{doc.page_content}"
        for doc in docs
    )


def _to_sources(docs: list[Document]) -> list[SourceChunk]:
    return [
        SourceChunk(
            doc_id=doc.metadata.get("doc_id", ""),
            filename=doc.metadata.get("filename", ""),
            page_number=doc.metadata.get("page_number"),
            text=doc.page_content[:300],
            score=float(doc.metadata.get("_score", 0.0)),
        )
        for doc in docs
    ]


def _check_citations(answer: str, docs: list[Document]) -> list[str]:
    unverified = find_unverified_citations(answer, docs)
    if unverified:
        UNVERIFIED_CITATIONS.inc()
        logger.warning(f"Answer cites sources that were not retrieved: {unverified}")
    return unverified


# ── sync path (/ask) ─────────────────────────────────────────────────────────

def get_answer(
    question: str,
    session_id: UUID,
    doc_id: Optional[UUID] = None,
    owner_id: Optional[str] = None,
) -> AnswerResponse:
    logger.info(f"Processing question for session {session_id}, doc_id={doc_id}: {question[:100]}")
    llm = _get_llm(streaming=False)
    chat_history = _chat_history(session_id, owner_id)

    # Condense follow-up into a standalone question only when history exists
    if chat_history:
        retrieval_question = (_CONDENSE_PROMPT | llm | StrOutputParser()).invoke(
            {"input": question, "chat_history": chat_history}
        )
        logger.debug(f"Condensed question: {retrieval_question}")
    else:
        retrieval_question = question

    docs = _make_retriever(doc_id, owner_id).invoke(retrieval_question)
    if not docs:
        # Nothing relevant: don't ask the model to answer from nothing.
        NO_ANSWER.inc()
        session_memory.add_turn(session_id, question, NO_ANSWER_TEXT, owner_id)
        return AnswerResponse(answer=NO_ANSWER_TEXT, sources=[], session_id=session_id)

    answer_text = (_QA_PROMPT | llm | StrOutputParser()).invoke(
        {"input": question, "chat_history": chat_history, "context": _format_context(docs)}
    )

    sources = _to_sources(docs)
    unverified = _check_citations(answer_text, docs)
    logger.info(f"Generated answer with {len(sources)} sources")
    session_memory.add_turn(session_id, question, answer_text, owner_id)
    return AnswerResponse(
        answer=answer_text, sources=sources, session_id=session_id, unverified_citations=unverified
    )


# ── async path (/ask/stream) ─────────────────────────────────────────────────

async def astream_answer(
    question: str,
    session_id: UUID,
    doc_id: Optional[UUID] = None,
    owner_id: Optional[str] = None,
) -> AsyncIterator[dict]:
    logger.info(f"Processing streaming question for session {session_id}, doc_id={doc_id}: {question[:100]}")
    llm = _get_llm(streaming=True)
    chat_history = _chat_history(session_id, owner_id)

    # Nothing below may block the event loop: LLM calls are awaited, and the
    # CPU/IO-bound retrieval (embedding + Chroma) runs in a worker thread.
    try:
        if chat_history:
            retrieval_question = await (_CONDENSE_PROMPT | llm | StrOutputParser()).ainvoke(
                {"input": question, "chat_history": chat_history}
            )
            logger.debug(f"Condensed question: {retrieval_question}")
        else:
            retrieval_question = question

        docs = await asyncio.to_thread(
            _make_retriever(doc_id, owner_id).invoke, retrieval_question
        )
    except Exception as exc:
        logger.error(f"Error preparing streaming answer: {exc}", exc_info=True)
        LLM_ERRORS.labels("stream_prepare").inc()
        yield {"type": "error", "data": "Failed to prepare an answer."}
        return

    if not docs:
        NO_ANSWER.inc()
        session_memory.add_turn(session_id, question, NO_ANSWER_TEXT, owner_id)
        yield {"type": "token", "data": NO_ANSWER_TEXT}
        yield {"type": "sources", "data": []}
        yield {"type": "done"}
        return

    answer_tokens: list[str] = []
    try:
        async for chunk in (_QA_PROMPT | llm | StrOutputParser()).astream(
            {"input": question, "chat_history": chat_history, "context": _format_context(docs)}
        ):
            answer_tokens.append(chunk)
            yield {"type": "token", "data": chunk}
    except Exception as exc:
        logger.error(f"Error streaming answer: {exc}", exc_info=True)
        LLM_ERRORS.labels("stream").inc()
        yield {"type": "error", "data": "Failed to generate an answer."}
        return

    sources = _to_sources(docs)
    logger.info(f"Generated streaming answer with {len(sources)} sources")
    answer_text = "".join(answer_tokens)
    session_memory.add_turn(session_id, question, answer_text, owner_id)
    unverified = _check_citations(answer_text, docs)
    if unverified:
        yield {"type": "citations", "data": {"unverified": unverified}}
    yield {"type": "sources", "data": [s.model_dump() for s in sources]}
    yield {"type": "done"}
