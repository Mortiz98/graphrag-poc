"""Evaluation runner: executes evaluations against truth sets."""

import json
from pathlib import Path

from app.core.retrieval import get_retrieval_engine

from .metrics import grounding_rate, mean_reciprocal_rank, ndcg_at_k, recall_at_k, relevance_at_k

TRUTH_SETS_DIR = Path(__file__).parent / "truth_sets"


def load_truth_set(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    items = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def _compute_keyword_relevance(retrieved: list, keywords: set[str]) -> set[str]:
    relevant_ids = set()
    for r in retrieved:
        text = f"{r.subject} {r.predicate} {r.object}".lower()
        if any(kw.lower() in text for kw in keywords):
            relevant_ids.add(r.chunk_id)
    return relevant_ids


def run_retrieval_eval(
    truth_set_path: str | Path,
    top_k: int = 5,
    scope: dict | None = None,
) -> dict:
    truth_set = load_truth_set(truth_set_path)
    if not truth_set:
        return {"error": "empty_truth_set", "total": 0}

    engine = get_retrieval_engine()
    results = {
        "total_questions": len(truth_set),
        "relevance_at_5": [],
        "relevance_at_3": [],
        "mrr": [],
        "ndcg_at_10": [],
        "recall_at_5": [],
    }

    for item in truth_set:
        question = item["question"]
        relevant_chunks = set(item.get("relevant_chunks", []))
        relevance_scores = item.get("relevance_scores", {})
        keywords = item.get("relevant_keywords", [])

        retrieved = engine.search_dense(query=question, top_k=max(top_k, 10), scope=scope)
        retrieved_ids = [r.chunk_id for r in retrieved if r.chunk_id]

        if not relevant_chunks and keywords:
            relevant_chunks = _compute_keyword_relevance(retrieved, set(keywords))
            relevance_scores = {cid: 1.0 for cid in relevant_chunks}

        results["relevance_at_5"].append(relevance_at_k(retrieved_ids, relevant_chunks, k=5))
        results["relevance_at_3"].append(relevance_at_k(retrieved_ids, relevant_chunks, k=3))
        results["mrr"].append(mean_reciprocal_rank(retrieved_ids, relevant_chunks))
        results["ndcg_at_10"].append(ndcg_at_k(retrieved_ids, relevance_scores, k=10))
        results["recall_at_5"].append(recall_at_k(retrieved_ids, relevant_chunks, k=5))

    summary = {"total_questions": len(truth_set)}
    for metric_name, values in results.items():
        if metric_name == "total_questions":
            continue
        if values:
            summary[f"avg_{metric_name}"] = round(sum(values) / len(values), 4)
            summary[f"min_{metric_name}"] = round(min(values), 4)
            summary[f"max_{metric_name}"] = round(max(values), 4)

    return summary


def run_grounding_eval(
    truth_set_path: str | Path,
    scope: dict | None = None,
) -> dict:
    truth_set = load_truth_set(truth_set_path)
    if not truth_set:
        return {"error": "empty_truth_set", "total": 0}

    engine = get_retrieval_engine()
    grounding_scores = []

    for item in truth_set:
        question = item["question"]
        retrieved = engine.search_dense(query=question, top_k=5, scope=scope)
        evidence_texts = [f"{r.subject} {r.predicate} {r.object}" for r in retrieved]
        answer = item.get("ideal_answer", "")
        if answer and evidence_texts:
            score = grounding_rate(answer, evidence_texts)
            grounding_scores.append(score)

    if not grounding_scores:
        return {"total": len(truth_set), "avg_grounding_rate": 0.0}

    return {
        "total": len(truth_set),
        "avg_grounding_rate": round(sum(grounding_scores) / len(grounding_scores), 4),
        "min_grounding_rate": round(min(grounding_scores), 4),
        "max_grounding_rate": round(max(grounding_scores), 4),
    }
