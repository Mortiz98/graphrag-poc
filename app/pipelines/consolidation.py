"""Consolidation pipeline: supersede outdated facts with newer ones."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from app.core import logger


@dataclass
class Fact:
    subject: str
    predicate: str
    object: str
    id: str = field(default_factory=lambda: str(uuid4()))
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    is_active: bool = True
    superseded_by: str | None = None
    source_doc: str = ""
    chunk_id: str = ""

    def to_payload(self) -> dict:
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "id": self.id,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "is_active": self.is_active,
            "superseded_by": self.superseded_by,
            "source_doc": self.source_doc,
            "chunk_id": self.chunk_id,
        }


def apply_supersession(
    old_fact: Fact,
    new_fact: Fact,
    *,
    now: datetime | None = None,
) -> tuple[Fact, Fact]:
    """Mark *old_fact* as superseded by *new_fact*.

    Sets temporal and active-status fields on both facts so that the old
    fact is retired and the new fact becomes the current version.

    Returns the updated ``(old_fact, new_fact)`` pair.
    """
    timestamp = now or datetime.now(timezone.utc)

    # Retire the old fact
    old_fact.valid_to = timestamp
    old_fact.is_active = False
    old_fact.superseded_by = new_fact.id

    # Activate the new fact
    new_fact.valid_from = timestamp
    new_fact.is_active = True

    logger.info(
        "fact_superseded",
        old_fact_id=old_fact.id,
        new_fact_id=new_fact.id,
        timestamp=timestamp.isoformat(),
    )

    return old_fact, new_fact


def persist_facts(
    facts: list[Fact],
    collection_name: str,
    vectors: list[list[float]],
) -> int:
    """Persist a list of facts (with pre-computed vectors) into Qdrant."""
    from qdrant_client.models import PointStruct

    from app.core.vectorstore import get_qdrant_client

    client = get_qdrant_client()
    points = [PointStruct(id=f.id, vector=vec, payload=f.to_payload()) for f, vec in zip(facts, vectors)]
    client.upsert(collection_name=collection_name, points=points)
    logger.info("facts_persisted", count=len(points))
    return len(points)
