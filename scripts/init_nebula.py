"""Initialize NebulaGraph schema for the GraphRAG PoC.

This script creates the space and all required tags and edges
in NebulaGraph. Run it after starting the Docker services.
"""

from app.config import get_settings
from app.core import logger
from app.core.graph import get_nebula_session

SCHEMA_STATEMENTS = [
    "CREATE SPACE IF NOT EXISTS graphrag (vid_type=FIXED_STRING(256), partition_num=1, replica_factor=1)",
]


SCHEMA_STATEMENTS_AFTER_SPACE = [
    "USE graphrag",
    "CREATE TAG IF NOT EXISTS entity (name string, type string, description string)",
    "CREATE TAG IF NOT EXISTS chunk (content string, source string, chunk_index int)",
    "CREATE EDGE IF NOT EXISTS related_to (relation string, weight double)",
    "CREATE EDGE IF NOT EXISTS contains_chunk (position int)",
    "CREATE EDGE IF NOT EXISTS same_as (confidence double)",
]

STORAGE_HOST = "nebula-storaged"
STORAGE_PORT = 9779


def _wait_for_storage(session, timeout: int = 60) -> None:
    import time

    logger.info("waiting_for_storage_host_to_come_online")
    start = time.time()
    while time.time() - start < timeout:
        result = session.execute("SHOW HOSTS")
        if result.is_succeeded():
            for row in result.rows():
                host_val = (
                    row.values[0].get_sVal().decode() if hasattr(row.values[0], "get_sVal") else str(row.values[0])
                )
                status_val = (
                    row.values[2].get_sVal().decode() if hasattr(row.values[2], "get_sVal") else str(row.values[2])
                )
                if host_val == STORAGE_HOST and status_val == "ONLINE":
                    logger.info("storage_host_online", host=STORAGE_HOST)
                    return
        time.sleep(2)
    raise TimeoutError(f"Storage host {STORAGE_HOST} did not come online within {timeout}s")


def init_schema() -> None:
    settings = get_settings()
    logger.info("initializing_nebula_schema", space=settings.nebula_space)

    with get_nebula_session() as session:
        _wait_for_storage(session)

        for stmt in SCHEMA_STATEMENTS:
            result = session.execute(stmt)
            if result.is_succeeded():
                logger.info("schema_ok", statement=stmt[:60])
            else:
                logger.error("schema_failed", statement=stmt[:60], error=result.error_msg())

        logger.info("waiting_for_space_creation")
        import time

        time.sleep(5)

        for stmt in SCHEMA_STATEMENTS_AFTER_SPACE:
            result = session.execute(stmt)
            if result.is_succeeded():
                logger.info("schema_ok", statement=stmt[:60])
            else:
                logger.error("schema_failed", statement=stmt[:60], error=result.error_msg())

    logger.info("schema_initialization_complete")


if __name__ == "__main__":
    init_schema()
