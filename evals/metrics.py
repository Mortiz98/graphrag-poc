"""Evaluation metrics: relevance@k, MRR, nDCG, grounding rate."""

import math


def relevance_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int = 5) -> float:
    if not relevant_ids or k <= 0:
        return 0.0
    top_k = retrieved_ids[:k]
    relevant_in_top_k = sum(1 for rid in top_k if rid in relevant_ids)
    return relevant_in_top_k / min(k, len(top_k)) if top_k else 0.0


def mean_reciprocal_rank(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    if not relevant_ids:
        return 0.0
    for i, rid in enumerate(retrieved_ids, start=1):
        if rid in relevant_ids:
            return 1.0 / i
    return 0.0


def ndcg_at_k(retrieved_ids: list[str], relevance_scores: dict[str, int], k: int = 10) -> float:
    if not relevance_scores:
        return 0.0
    dcg = 0.0
    for i, rid in enumerate(retrieved_ids[:k], start=1):
        rel = relevance_scores.get(rid, 0)
        dcg += rel / math.log2(i + 1)

    ideal_scores = sorted(relevance_scores.values(), reverse=True)[:k]
    idcg = 0.0
    for i, rel in enumerate(ideal_scores, start=1):
        idcg += rel / math.log2(i + 1)

    return dcg / idcg if idcg > 0 else 0.0


def grounding_rate(answer: str, evidence_texts: list[str]) -> float:
    if not answer or not evidence_texts:
        return 0.0
    supported_claims = 0
    total_claims = 0
    sentences = [s.strip() for s in answer.split(".") if s.strip()]
    if not sentences:
        return 0.0
    for sentence in sentences:
        total_claims += 1
        for evidence in evidence_texts:
            evidence_lower = evidence.lower()
            words = [w for w in sentence.lower().split() if len(w) > 3]
            overlap = sum(1 for w in words if w in evidence_lower)
            if words and overlap / len(words) > 0.3:
                supported_claims += 1
                break
    return supported_claims / total_claims if total_claims > 0 else 0.0


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int = 5) -> float:
    if not relevant_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    return len(top_k & relevant_ids) / len(relevant_ids)
