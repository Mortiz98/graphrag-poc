from contextlib import contextmanager

from nebula3.Config import Config as NebulaConfig
from nebula3.gclient.net import ConnectionPool

from app.config import get_settings
from app.core import logger


def _build_nebula_config() -> NebulaConfig:
    config = NebulaConfig()
    config.max_connection_pool_size = 10
    return config


@contextmanager
def get_nebula_session():
    settings = get_settings()
    pool = ConnectionPool()
    config = _build_nebula_config()

    connected = pool.init(
        [(settings.nebula_host, settings.nebula_port)],
        config,
    )
    if not connected:
        raise ConnectionError("Failed to connect to NebulaGraph")

    session = pool.get_session(settings.nebula_user, settings.nebula_password)
    try:
        yield session
    finally:
        session.release()
        pool.close()


async def check_nebula_health() -> bool:
    try:
        with get_nebula_session() as session:
            result = session.execute("SHOW HOSTS")
            return result.is_succeeded()
    except Exception as e:
        logger.error("nebula_health_check_failed", error=str(e))
        return False
