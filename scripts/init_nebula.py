import time

from app.config import get_settings
from app.core import logger
from app.core.graph import get_nebula_session
from app.models.graph_schema import ALL_DOMAIN_SCHEMAS

STORAGE_HOST = "nebula-storaged"
STORAGE_PORT = 9779

SCHEMA_STATEMENTS_AFTER_SPACE = [
    "USE graphrag",
    *ALL_DOMAIN_SCHEMAS,
]


def _add_storage_host(session) -> None:
    result = session.execute("SHOW HOSTS")
    registered = False
    if result.is_succeeded():
        for row in result.rows():
            host_val = row.values[0].get_sVal().decode() if hasattr(row.values[0], "get_sVal") else str(row.values[0])
            if host_val == STORAGE_HOST:
                registered = True
                break

    if not registered:
        stmt = f'ADD HOSTS "{STORAGE_HOST}":{STORAGE_PORT}'
        result = session.execute(stmt)
        if result.is_succeeded():
            logger.info("storage_host_added", host=STORAGE_HOST)
        else:
            logger.warning("add_host_failed", error=result.error_msg())


def _wait_for_storage(session, timeout: int = 120) -> None:
    logger.info("waiting_for_storage_host_to_come_online")
    start = time.time()
    while time.time() - start < timeout:
        result = session.execute("SHOW HOSTS")
        if result.is_succeeded():
            for row in result.rows():
                host_val = row.values[0].get_sVal().decode() if hasattr(row.values[0], "get_sVal") else str(row.values[0])
                status_val = row.values[2].get_sVal().decode() if hasattr(row.values[2], "get_sVal") else str(row.values[2])
                if host_val == STORAGE_HOST and status_val == "ONLINE":
                    logger.info("storage_host_online", host=STORAGE_HOST)
                    return
        time.sleep(3)
    logger.warning("storage_host_timeout", host=STORAGE_HOST)


def init_schema() -> None:
    settings = get_settings()
    logger.info("initializing_nebula_schema", space=settings.nebula_space)

    with get_nebula_session() as session:
        _add_storage_host(session)
        _wait_for_storage(session)

        result = session.execute("CREATE SPACE IF NOT EXISTS graphrag (vid_type=FIXED_STRING(256), partition_num=1, replica_factor=1)")
        if result.is_succeeded():
            logger.info("space_created_or_exists")
        else:
            logger.error("space_creation_failed", error=result.error_msg())

        logger.info("waiting_for_space_creation")
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
