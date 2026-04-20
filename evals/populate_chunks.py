"""Populate relevant_chunks in truth set by running search_dense for each question.

Requires Docker running with Qdrant + NebulaGraph + data ingested.

Usage:
    PYTHONPATH=. uv run python evals/populate_chunks.py
"""

import json
from pathlib import Path

from app.core.retrieval import get_retrieval_engine

TRUTH_SET_PATH = Path(__file__).parent / "truth_sets" / "support_qa.jsonl"


def populate_chunks(top_k: int = 10) -> int:
    engine = get_retrieval_engine()
    lines = TRUTH_SET_PATH.read_text().strip().split("\n")
    updated = 0

    new_lines = []
    for line in lines:
        item = json.loads(line)
        question = item["question"]

        results = engine.search_dense(
            query=question,
            top_k=top_k,
            scope={"system": "support"},
            active_only=True,
        )

        chunk_ids = [r.chunk_id for r in results if r.chunk_id]
        item["relevant_chunks"] = chunk_ids
        new_lines.append(json.dumps(item, ensure_ascii=False))
        updated += 1

    TRUTH_SET_PATH.write_text("\n".join(new_lines) + "\n")
    return updated


if __name__ == "__main__":
    count = populate_chunks()
    print(f"Populated chunks for {count} questions in {TRUTH_SET_PATH}")
