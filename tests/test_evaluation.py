from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture
def mock_ragas_evaluate():
    """Patch ragas.evaluate to return a canned EvaluationResult."""
    mock_result = MagicMock()
    mock_result.to_pandas.return_value = pd.DataFrame([{
        "faithfulness": 0.9,
        "answer_relevancy": 0.85,
        "context_precision": 0.8,
    }])
    with patch("services.evaluation.evaluate", return_value=mock_result):
        yield mock_result


@pytest.fixture
def mock_llm_emb():
    """Patch _make_llm_and_embeddings so no real models are loaded."""
    with (
        patch("services.evaluation.LangchainLLMWrapper"),
        patch("services.evaluation.LangchainEmbeddingsWrapper"),
        patch("services.evaluation.ChatGroq"),
        patch("services.evaluation.HuggingFaceEmbeddings"),
    ):
        yield


def test_score_single_returns_expected_keys(mock_llm_emb, mock_ragas_evaluate):
    from services.evaluation import score_single

    result = score_single(
        question="What is RAG?",
        answer="RAG stands for Retrieval-Augmented Generation.",
        contexts=["RAG combines retrieval with generation."],
        ground_truth="RAG is Retrieval-Augmented Generation.",
    )

    assert set(result.keys()) == {"faithfulness", "answer_relevancy", "context_precision"}
    assert result["faithfulness"] == pytest.approx(0.9)
    assert result["answer_relevancy"] == pytest.approx(0.85)
    assert result["context_precision"] == pytest.approx(0.8)


def test_score_single_no_ground_truth_omits_context_precision(mock_llm_emb, mock_ragas_evaluate):
    mock_ragas_evaluate.to_pandas.return_value = pd.DataFrame([{
        "faithfulness": 0.9,
        "answer_relevancy": 0.85,
    }])

    from services.evaluation import score_single

    result = score_single(
        question="What is RAG?",
        answer="RAG stands for Retrieval-Augmented Generation.",
        contexts=["RAG combines retrieval with generation."],
    )

    assert result["context_precision"] is None
    assert result["faithfulness"] == pytest.approx(0.9)


def test_score_single_handles_nan_as_none(mock_llm_emb, mock_ragas_evaluate):
    mock_ragas_evaluate.to_pandas.return_value = pd.DataFrame([{
        "faithfulness": float("nan"),
        "answer_relevancy": 0.7,
        "context_precision": float("nan"),
    }])

    from services.evaluation import score_single

    result = score_single(
        question="Q?",
        answer="A.",
        contexts=["ctx"],
        ground_truth="GT",
    )

    assert result["faithfulness"] is None
    assert result["answer_relevancy"] == pytest.approx(0.7)
