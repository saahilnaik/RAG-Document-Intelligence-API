"""Quality gate over RAGAS results, used by scripts/evaluate.py (and CI)."""
from statistics import mean
from typing import Optional

METRICS = ("faithfulness", "answer_relevancy", "context_precision")


def parse_thresholds(items: list[str]) -> dict[str, float]:
    """Parse ["faithfulness=0.7", ...] into {"faithfulness": 0.7}."""
    out: dict[str, float] = {}
    for item in items:
        name, sep, value = item.partition("=")
        if not sep or name not in METRICS:
            raise ValueError(f"Bad threshold {item!r}; expected one of {METRICS} as name=value")
        out[name] = float(value)
    return out


def mean_scores(results: list[dict]) -> dict[str, Optional[float]]:
    """Mean per metric, ignoring samples where the metric is missing/NaN."""
    means: dict[str, Optional[float]] = {}
    for m in METRICS:
        vals = [r[m] for r in results if r.get(m) is not None and r[m] == r[m]]
        means[m] = mean(vals) if vals else None
    return means


def failures(results: list[dict], thresholds: dict[str, float]) -> list[str]:
    """Human-readable reasons the run fails the gate (empty list = pass).

    A metric with a threshold but no scores at all counts as a failure: a silent
    scoring outage must not look like a pass.
    """
    means = mean_scores(results)
    problems = []
    for metric, minimum in thresholds.items():
        value = means.get(metric)
        if value is None:
            problems.append(f"{metric}: no scores produced (required >= {minimum})")
        elif value < minimum:
            problems.append(f"{metric}: mean {value:.3f} < required {minimum}")
    return problems
