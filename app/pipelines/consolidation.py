"""Consolidation pipeline: shared 7-step memory write pipeline.

Steps: capture → extract → classify → consolidate → deduplicate → supersede → provenance.

Both Sistema A (ingestion) and Sistema B (fact recording) use this pipeline.
"""

from datetime import datetime, timezone
from uuid import uuid4

from app.core import logger
from app.core.retrieval import get_retrieval_engine
from app.core.vectorstore import ensure_collection_exists, get_qdrant_client
from app.models.schemas import CaseMetadata, FactMetadata

MEMORY_TYPE_STATE = "state"
MEMORY_TYPE_EPISODIC = "episodic"
MEMORY_TYPE_SEMANTIC = "semantic"
MEMORY_TYPE_PROCEDURAL = "procedural"

MEMORY_TYPES = {MEMORY_TYPE_STATE, MEMORY_TYPE_EPISODIC, MEMORY_TYPE_SEMANTIC, MEMORY_TYPE_PROCEDURAL}


def classify_memory(fact_type: str | None = None, system: str = "support") -> str:
    if fact_type == "fact":
        return MEMORY_TYPE_STATE
    if fact_type == "episode":
        return MEMORY_TYPE_EPISODIC
    if fact_type == "commitment":
        return MEMORY_TYPE_STATE
    if fact_type == "stakeholder":
        return MEMORY_TYPE_STATE
    if fact_type == "preference":
        return MEMORY_TYPE_PROCEDURAL
    if system == "support":
        return MEMORY_TYPE_SEMANTIC
    return MEMORY_TYPE_EPISODIC


def deduplicate_against_existing(
    new_triplets: list[dict],
    system: str = "support",
    account_id: str | None = None,
    similarity_threshold: float = 0.95,
) -> list[dict]:
    engine = get_retrieval_engine()
    unique_triplets = []
    for triplet in new_triplets:
        text = f"{triplet.get('subject', '')} {triplet.get('predicate', '')} {triplet.get('object', '')}"
        scope = {"system": system}
        if account_id:
            scope["account_id"] = account_id
        existing = engine.search_dense(query=text, top_k=3, min_score=similarity_threshold, scope=scope)
        is_dup = False
        for r in existing:
            key_new = f"{triplet.get('subject', '')}|{triplet.get('predicate', '')}|{triplet.get('object', '')}".lower()
            key_exist = f"{r.subject}|{r.predicate}|{r.object}".lower()
            if key_new == key_exist:
                is_dup = True
                break
        if not is_dup:
            unique_triplets.append(triplet)
        else:
            logger.info("deduplicated_triplet", subject=triplet.get("subject"), predicate=triplet.get("predicate"))
    return unique_triplets


def apply_supersession(
    new_facts: list[dict],
    system: str = "support",
    account_id: str | None = None,
) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    superseded_count = 0
    for fact in new_facts:
        if fact.get("fact_type") not in ("fact", "commitment"):
            continue
        supersedes_id = fact.get("supersedes")
        if not supersedes_id:
            continue
        try:
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            client = get_qdrant_client()
            from app.config import get_settings

            settings = get_settings()
            ensure_collection_exists(client, settings.qdrant_collection_name)

            client.set_payload(
                collection_name=settings.qdrant_collection_name,
                payload={"valid_to": now, "superseded_by": fact.get("id", "unknown"), "is_active": False},
                points=[supersedes_id],
                filters=Filter(
                    must=[
                        FieldCondition(key="system", match=MatchValue(value=system)),
                    ]
                    + ([FieldCondition(key="account_id", match=MatchValue(value=account_id))] if account_id else [])
                ),
            )
            superseded_count += 1
        except Exception as e:
            logger.warning("supersession_failed", supersedes_id=supersedes_id, error=str(e))
    if superseded_count:
        logger.info("supersession_applied", count=superseded_count)
    return new_facts


def run_consolidation_pipeline(
    triplets: list[dict],
    system: str = "support",
    source_doc: str = "",
    case_metadata: CaseMetadata | None = None,
    fact_metadata: FactMetadata | None = None,
    skip_dedup: bool = False,
    skip_supersede: bool = False,
) -> list[dict]:
    batch_timestamp = datetime.now(timezone.utc).isoformat()
    ingestion_batch_id = str(uuid4())[:8]
    account_id = fact_metadata.account_id if fact_metadata else None
    fact_type = fact_metadata.fact_type if fact_metadata else None

    for t in triplets:
        t["system"] = system
        t["source_doc"] = source_doc
        t["created_at"] = batch_timestamp
        t["ingestion_batch"] = ingestion_batch_id
        t["memory_type"] = classify_memory(fact_type, system)

        if fact_metadata:
            for key, value in fact_metadata.model_dump(exclude_none=True).items():
                if key not in t:
                    t[key] = value
        if case_metadata:
            for key, value in case_metadata.model_dump(exclude_none=True).items():
                if key not in t:
                    t[key] = value

    if not skip_dedup:
        triplets = deduplicate_against_existing(triplets, system=system, account_id=account_id)

    if not skip_supersede:
        triplets = apply_supersession(triplets, system=system, account_id=account_id)

    logger.info(
        "consolidation_completed",
        system=system,
        source=source_doc,
        total_input=len(triplets),
        memory_type=fact_type,
        batch=ingestion_batch_id,
    )

    return triplets
