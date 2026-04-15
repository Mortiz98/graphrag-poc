"""Seed the GraphRAG system with sample data for testing and demos."""

from pathlib import Path

from app.core import logger
from app.pipelines.ingestion import ingest_document

SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "test_data"


def seed(sample_file: str = "sample.txt") -> dict:
    file_path = SAMPLE_DATA_DIR / sample_file
    if not file_path.exists():
        raise FileNotFoundError(f"Sample file not found: {file_path}")

    logger.info("seeding_started", file=str(file_path))
    result = ingest_document(file_path)
    logger.info("seeding_completed", **result)
    return result


if __name__ == "__main__":
    seed()
