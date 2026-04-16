"""Memory writer: writes facts/episodes to Qdrant with metadata."""

from datetime import datetime, timezone
from uuid import uuid4

from qdrant_client.models import PointStruct

from app.core import logger
from app.core.embeddings import get_embeddings
from app.core.vectorstore import ensure_collection_exists, get_qdrant_client


def write_facts_to_store(
    facts: list[dict],
    system: str = "support",
) -> int:
    if not facts:
        return 0

    from app.config import get_settings

    settings = get_settings()
    client = get_qdrant_client()
    ensure_collection_exists(client, settings.qdrant_collection_name)
    embeddings = get_embeddings()

    all_texts = []
    all_payloads = []
    all_ids = []

    for fact in facts:
        point_id = fact.get("id") or str(uuid4())
        text = f"{fact.get('subject', '')} {fact.get('predicate', '')} {fact.get('object', '')}"
        all_ids.append(point_id)
        all_texts.append(text)
        all_payloads.append(fact)

    batch_size = 20
    total_stored = 0
    for i in range(0, len(all_texts), batch_size):
        batch_texts = all_texts[i : i + batch_size]
        batch_ids = all_ids[i : i + batch_size]
        batch_payloads = all_payloads[i : i + batch_size]

        vectors = embeddings.embed_documents(batch_texts)

        points = [
            PointStruct(id=bid, vector=vec, payload=payload)
            for bid, vec, payload in zip(batch_ids, vectors, batch_payloads)
        ]
        client.upsert(collection_name=settings.qdrant_collection_name, points=points)
        total_stored += len(points)

    logger.info("facts_written_to_store", system=system, count=total_stored)
    return total_stored


def record_fact(
    subject: str,
    predicate: str,
    object_: str,
    system: str = "am",
    account_id: str | None = None,
    fact_type: str = "fact",
    valid_from: str | None = None,
    valid_to: str | None = None,
    supersedes: str | None = None,
    confidence: float | None = None,
    source_doc: str = "",
) -> str:
    now = datetime.now(timezone.utc).isoformat()
    fact_id = str(uuid4())

    fact = {
        "id": fact_id,
        "subject": subject,
        "predicate": predicate,
        "object": object_,
        "system": system,
        "account_id": account_id,
        "fact_type": fact_type,
        "valid_from": valid_from or now,
        "valid_to": valid_to,
        "supersedes": supersedes,
        "confidence": confidence,
        "source_doc": source_doc,
        "created_at": now,
        "memory_type": fact_type,
    }

    write_facts_to_store([fact], system=system)
    logger.info("fact_recorded", fact_id=fact_id, subject=subject, system=system)
    return fact_id


def supersede_fact(
    old_fact_id: str,
    new_subject: str,
    new_predicate: str,
    new_object: str,
    system: str = "am",
    account_id: str | None = None,
    reason: str = "",
) -> str:
    now = datetime.now(timezone.utc).isoformat()
    new_id = record_fact(
        subject=new_subject,
        predicate=new_predicate,
        object_=new_object,
        system=system,
        account_id=account_id,
        fact_type="fact",
        supersedes=old_fact_id,
    )

    try:
        from app.config import get_settings

        settings = get_settings()
        client = get_qdrant_client()
        client.set_payload(
            collection_name=settings.qdrant_collection_name,
            payload={"valid_to": now, "superseded_by": new_id},
            points=[old_fact_id],
        )
        logger.info("fact_superseded", old_id=old_fact_id, new_id=new_id)
    except Exception as e:
        logger.warning("supersede_payload_update_failed", old_id=old_fact_id, error=str(e))

    return new_id
