"""CLI batch evaluator: reads a JSONL file of Q/A pairs, runs the full RAG
pipeline for each, scores with RAGAS, prints a table, and writes JSON output.

Usage:
    venv\\Scripts\\python scripts/evaluate.py eval_dataset/sample_qa.jsonl [--doc-id <uuid>]

    # CI-style: ingest a file first, then exit 1 if mean scores are too low
    python scripts/evaluate.py eval_dataset/sample_qa.jsonl --ingest eval_dataset/sample.pdf --fail-under faithfulness=0.7 answer_relevancy=0.6
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

# Ensure project root is on sys.path when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("GROQ_API_KEY", "")  # will be overridden by .env via Settings

from core.config import get_settings  # noqa: E402 — after sys.path setup
from services.eval_gate import failures, mean_scores, parse_thresholds  # noqa: E402
from services.evaluation import score_batch  # noqa: E402
from services.qa import get_answer  # noqa: E402


def _load_samples(path: str) -> list[dict]:
    samples = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples


EVAL_OWNER = "eval"


def _ingest(path: str) -> UUID:
    """Ingest a document into the vector store under a throwaway owner."""
    from services.ingestion import run_ingestion

    file = Path(path)
    doc_id = uuid4()
    n = run_ingestion(doc_id, file, file.suffix.lower(), file.name, EVAL_OWNER)
    print(f"Ingested {file.name}: {n} chunks (doc_id={doc_id})")
    return doc_id


def _run_pipeline(question: str, doc_id_str: str | None, owner_id: str | None = None) -> tuple[str, list[str]]:
    session_id = uuid4()
    doc_id = UUID(doc_id_str) if doc_id_str else None
    response = get_answer(question, session_id, doc_id, owner_id)
    contexts = [s.text for s in response.sources]
    return response.answer, contexts


def _print_table(results: list[dict], questions: list[str]) -> None:
    header = f"{'#':<4} {'Question':<45} {'Faith':>7} {'Rel':>7} {'Prec':>7}"
    print("\n" + header)
    print("-" * len(header))
    for i, (q, r) in enumerate(zip(questions, results, strict=False), 1):
        faith = f"{r['faithfulness']:.3f}" if r["faithfulness"] is not None else "  n/a"
        rel = f"{r['answer_relevancy']:.3f}" if r["answer_relevancy"] is not None else "  n/a"
        prec = f"{r['context_precision']:.3f}" if r["context_precision"] is not None else "  n/a"
        print(f"{i:<4} {q[:44]:<45} {faith:>7} {rel:>7} {prec:>7}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch RAGAS evaluator")
    parser.add_argument("jsonl", help="Path to JSONL file with question/ground_truth pairs")
    parser.add_argument("--doc-id", default=None, help="Filter retrieval to a specific doc_id")
    parser.add_argument("--ingest", default=None, help="Ingest this file first and evaluate against it")
    parser.add_argument(
        "--fail-under", nargs="+", default=[], metavar="METRIC=MIN",
        help="Exit 1 if a mean score is below its minimum, e.g. faithfulness=0.7",
    )
    args = parser.parse_args()
    thresholds = parse_thresholds(args.fail_under)

    get_settings()  # validate config / load .env early

    owner_id = None
    if args.ingest:
        args.doc_id = str(_ingest(args.ingest))
        owner_id = EVAL_OWNER

    samples = _load_samples(args.jsonl)
    print(f"Loaded {len(samples)} samples from {args.jsonl}")

    # Run the full RAG pipeline for each sample
    enriched = []
    for i, s in enumerate(samples, 1):
        print(f"  [{i}/{len(samples)}] Running pipeline for: {s['question'][:60]}")
        answer, contexts = _run_pipeline(s["question"], args.doc_id, owner_id)
        enriched.append({
            "question": s["question"],
            "answer": answer,
            "contexts": contexts,
            "ground_truth": s.get("ground_truth"),
        })
        if i < len(samples):
            time.sleep(2)  # respect Groq 30 RPM limit

    print("\nScoring with RAGAS (this may take a moment)...")
    scores = score_batch(enriched)

    _print_table(scores, [e["question"] for e in enriched])

    # Write JSON output
    output_dir = Path("eval_results")
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{timestamp}.json"
    output_data = [
        {**enriched[i], **scores[i]}
        for i in range(len(enriched))
    ]
    output_path.write_text(json.dumps(output_data, indent=2))
    print(f"Results written to {output_path}")

    means = mean_scores(scores)
    print("Mean scores: " + ", ".join(f"{k}={v:.3f}" if v is not None else f"{k}=n/a" for k, v in means.items()))
    problems = failures(scores, thresholds)
    if problems:
        print("\nQUALITY GATE FAILED:\n  " + "\n  ".join(problems))
        sys.exit(1)
    if thresholds:
        print("Quality gate passed.")


if __name__ == "__main__":
    main()
