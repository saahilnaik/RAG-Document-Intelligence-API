"""Minimal BM25 (Okapi) so keyword search needs no extra dependency."""
import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the to was were will with".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


class BM25Index:
    def __init__(self, texts: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self._tfs: list[Counter] = [Counter(tokenize(t)) for t in texts]
        self._lens = [sum(tf.values()) for tf in self._tfs]
        n = len(texts)
        self._avgdl = (sum(self._lens) / n) if n else 0.0
        df: Counter = Counter()
        for tf in self._tfs:
            df.update(tf.keys())
        # BM25+ style idf (never negative), so common terms can't subtract score.
        self._idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def __len__(self) -> int:
        return len(self._tfs)

    def top_k(self, query: str, k: int) -> list[tuple[int, float]]:
        """Return up to k (doc_index, score) pairs with score > 0, best first."""
        terms = [t for t in set(tokenize(query)) if t in self._idf]
        if not terms or not self._avgdl:
            return []
        scored = []
        for i, tf in enumerate(self._tfs):
            score = 0.0
            norm = self.k1 * (1 - self.b + self.b * self._lens[i] / self._avgdl)
            for t in terms:
                f = tf.get(t, 0)
                if f:
                    score += self._idf[t] * f * (self.k1 + 1) / (f + norm)
            if score > 0:
                scored.append((i, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]
