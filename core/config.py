from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GROQ_API_KEY: str
    GROQ_CHAT_MODEL: str = "llama-3.3-70b-versatile"
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_TOKENS: int = 1024

    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DEVICE: str = "cpu"

    CHROMA_PERSIST_DIR: str = "./data/chroma"
    CHROMA_COLLECTION: str = "documents"

    UPLOAD_DIR: str = "./data/uploads"
    MAX_UPLOAD_SIZE_MB: int = 25
    ALLOWED_EXTENSIONS: set[str] = {".pdf", ".txt", ".docx", ".md"}

    RETRIEVAL_K: int = 5

    # Retrieval pipeline: semantic + BM25 -> RRF fusion -> cross-encoder rerank -> threshold
    HYBRID_ENABLED: bool = True
    HYBRID_MAX_CHUNKS: int = 50000  # skip keyword search beyond this many chunks in scope
    RETRIEVAL_CANDIDATES: int = 20  # candidates per retriever before reranking
    RERANK_ENABLED: bool = True
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    # Minimum final score for a chunk to be used. With the reranker on, scores are
    # sigmoid(logit) in [0,1] (irrelevant text is typically < 0.001). With it off,
    # scores are cosine similarity, where you'd want ~0.3+.
    MIN_RELEVANCE_SCORE: float = 0.01

    # LLM resilience
    LLM_TIMEOUT_SECONDS: float = 60.0
    LLM_MAX_RETRIES: int = 3
    GROQ_FALLBACK_MODEL: str = "llama-3.1-8b-instant"  # "" disables the fallback
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    MAX_CONVERSATION_TURNS: int = 5

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Auth: JSON map of API key -> user id, e.g. {"k_abc123": "alice"}.
    # Every non-health endpoint requires the `X-API-Key` header when AUTH_ENABLED.
    AUTH_ENABLED: bool = True
    API_KEYS: dict[str, str] = {}

    # Shared state. All optional: unset => in-process fallbacks (single-instance dev).
    #   DATABASE_URL  e.g. postgresql+psycopg://user:pw@db:5432/rag  (document registry)
    #   REDIS_URL     e.g. redis://redis:6379/0  (session memory + ingestion queue)
    #   CHROMA_HOST   run Chroma as a server so the API and worker can share it
    DATABASE_URL: str = ""
    REDIS_URL: str = ""
    CHROMA_HOST: str = ""
    CHROMA_PORT: int = 8000

    SESSION_TTL_SECONDS: int = 86400
    INGEST_MAX_TRIES: int = 3
    INGEST_STALE_MINUTES: int = 30

    # Observability
    ENVIRONMENT: str = "development"
    LOG_FORMAT: str = "text"  # "json" in containers
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: str = ""

    # Per-user limits
    MAX_DOCS_PER_USER: int = 50
    MAX_QUESTION_CHARS: int = 2000


@lru_cache
def get_settings() -> Settings:
    return Settings()
