from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    doc_id: UUID
    filename: str
    status: Literal["processing"] = "processing"


class DocumentStatus(BaseModel):
    doc_id: UUID
    filename: str
    status: Literal["processing", "ready", "failed"]
    error: Optional[str] = None
    created_at: datetime
    chunk_count: Optional[int] = None
    # Internal tenant key; never serialized to clients.
    owner_id: str = Field(default="anonymous", exclude=True)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: UUID
    doc_id: Optional[UUID] = None


class SourceChunk(BaseModel):
    doc_id: str
    filename: str
    page_number: Optional[int] = None
    text: str
    score: float


class AnswerResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
    session_id: UUID
    # Citations in the answer that match no retrieved chunk (possible hallucination).
    unverified_citations: list[str] = Field(default_factory=list)


class EvaluateRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=20000)
    contexts: list[str] = Field(max_length=20)
    ground_truth: Optional[str] = Field(default=None, max_length=20000)


class EvaluateResponse(BaseModel):
    faithfulness: Optional[float] = None
    answer_relevancy: Optional[float] = None
    context_precision: Optional[float] = None
