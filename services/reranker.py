import logging
import math
import threading
from typing import Optional

from core.config import get_settings

logger = logging.getLogger(__name__)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(min(x, 50.0), -50.0)))


class Reranker:
    """Cross-encoder relevance scoring of (query, passage) pairs.

    Much more accurate than comparing embeddings, but too slow to run over the
    whole corpus, so it only re-scores the fused shortlist. Loaded lazily.
    """

    def __init__(self):
        self._model = None
        self._lock = threading.Lock()

    def _ensure_loaded(self):
        if self._model is not None:
            return
        with self._lock:
            if self._model is None:
                from sentence_transformers import CrossEncoder

                settings = get_settings()
                self._model = CrossEncoder(settings.RERANKER_MODEL, device=settings.EMBEDDING_DEVICE)

    def score(self, query: str, passages: list[str]) -> Optional[list[float]]:
        """Relevance in [0, 1] per passage, or None if the model is unavailable."""
        if not passages:
            return []
        try:
            self._ensure_loaded()
            logits = self._model.predict([(query, p) for p in passages], show_progress_bar=False)
            return [_sigmoid(float(x)) for x in logits]
        except Exception:
            logger.error("Reranker failed; falling back to fused order", exc_info=True)
            return None


reranker = Reranker()
