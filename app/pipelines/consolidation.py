"""Consolidation pipeline: supersede outdated facts with newer ones."""

from datetime import datetime, timezone

from qdrant_client.models import PointStruct

from app.core import logger


def apply_supersession(
    old_fact_id: str,
    old_fact_payload: dict,
    new_fact_id: str,
    new_fact_payload: dict,
    client,
    collection_name: str,
) -> None:
    """Mark *old_fact* as superseded by *new_fact* and persist both.

    The function mutates the supplied payload dicts in-place and then writes
    the changes to Qdrant so that:

    * the old fact receives ``is_active=False``, ``valid_to=<now>``, and
      ``superseded_by=<new_fact_id>``;
    * the new fact receives ``is_active=True`` and ``valid_from=<now>``.

    Only the Qdrant client is touched; no other internal logic is mocked.
    """
    now = datetime.now(timezone.utc).isoformat()

    # ---- old fact: mark as superseded ----
    old_fact_payload["is_active"] = False
    old_fact_payload["valid_to"] = now
    old_fact_payload["superseded_by"] = new_fact_id

    # ---- new fact: mark as active ----
    new_fact_payload["is_active"] = True
    new_fact_payload["valid_from"] = now

    # ---- persist to Qdrant ----
    # Update only the changed payload keys on the old fact (no vector re-embed).
    client.set_payload(
        collection_name=collection_name,
        payload={
            "is_active": False,
            "valid_to": now,
            "superseded_by": new_fact_id,
        },
        points=[old_fact_id],
    )

    # Upsert the new fact.  The caller is expected to have computed a vector
    # already and stored it under the ``_vector`` key; we pop it out before
    # persisting the payload so it doesn't end up as a Qdrant payload field.
    vector = new_fact_payload.pop("_vector", [])
    client.upsert(
        collection_name=collection_name,
        points=[
            PointStruct(
                id=new_fact_id,
                vector=vector,
                payload=new_fact_payload,
            ),
        ],
    )

    logger.info(
        "supersession_applied",
        old_fact_id=old_fact_id,
        new_fact_id=new_fact_id,
    )
