from typing import Optional

from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import answer_relevancy, context_precision, faithfulness

from core.config import get_settings


def _make_llm_and_embeddings():
    settings = get_settings()
    llm = LangchainLLMWrapper(
        ChatGroq(
            api_key=settings.GROQ_API_KEY,
            model=settings.GROQ_CHAT_MODEL,
            temperature=0.0,
        )
    )
    emb = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(
            model_name=settings.EMBEDDING_MODEL,
            model_kwargs={"device": settings.EMBEDDING_DEVICE},
            encode_kwargs={"normalize_embeddings": True},
        )
    )
    return llm, emb


def score_single(
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: Optional[str] = None,
) -> dict[str, Optional[float]]:
    llm, emb = _make_llm_and_embeddings()

    sample = SingleTurnSample(
        user_input=question,
        response=answer,
        retrieved_contexts=contexts,
        reference=ground_truth,
    )
    dataset = EvaluationDataset(samples=[sample])

    metrics = [faithfulness, answer_relevancy]
    if ground_truth:
        metrics.append(context_precision)

    result = evaluate(
        dataset,
        metrics=metrics,
        llm=llm,
        embeddings=emb,
        show_progress=False,
        raise_exceptions=False,
    )

    scores = result.to_pandas().iloc[0]
    return {
        "faithfulness": _safe_float(scores.get("faithfulness")),
        "answer_relevancy": _safe_float(scores.get("answer_relevancy")),
        "context_precision": _safe_float(scores.get("context_precision")) if ground_truth else None,
    }


def score_batch(
    samples: list[dict],
) -> list[dict[str, Optional[float]]]:
    llm, emb = _make_llm_and_embeddings()

    ragas_samples = [
        SingleTurnSample(
            user_input=s["question"],
            response=s["answer"],
            retrieved_contexts=s["contexts"],
            reference=s.get("ground_truth"),
        )
        for s in samples
    ]
    dataset = EvaluationDataset(samples=ragas_samples)

    has_ground_truth = any(s.get("ground_truth") for s in samples)
    metrics = [faithfulness, answer_relevancy]
    if has_ground_truth:
        metrics.append(context_precision)

    result = evaluate(
        dataset,
        metrics=metrics,
        llm=llm,
        embeddings=emb,
        show_progress=True,
        raise_exceptions=False,
    )

    df = result.to_pandas()
    rows = []
    for _, row in df.iterrows():
        rows.append({
            "faithfulness": _safe_float(row.get("faithfulness")),
            "answer_relevancy": _safe_float(row.get("answer_relevancy")),
            "context_precision": _safe_float(row.get("context_precision")),
        })
    return rows


def _safe_float(val) -> Optional[float]:
    try:
        f = float(val)
        return None if f != f else f  # NaN check
    except (TypeError, ValueError):
        return None
