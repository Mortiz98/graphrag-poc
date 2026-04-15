import atexit
import threading

from nebula3.Config import Config as NebulaConfig
from nebula3.gclient.net import ConnectionPool

from app.config import get_settings
from app.core import logger

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def _build_nebula_config() -> NebulaConfig:
    config = NebulaConfig()
    config.max_connection_pool_size = 10
    return config


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is not None:
        return _pool

    with _pool_lock:
        if _pool is not None:
            return _pool

        settings = get_settings()
        pool = ConnectionPool()
        config = _build_nebula_config()

        connected = pool.init(
            [(settings.nebula_host, settings.nebula_port)],
            config,
        )
        if not connected:
            raise ConnectionError("Failed to connect to NebulaGraph")

        _pool = pool
        atexit.register(_close_pool)
        return _pool


def _close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def reset_pool() -> None:
    _close_pool()


class NebulaSession:
    def __init__(self):
        self._session = None

    def __enter__(self):
        pool = _get_pool()
        settings = get_settings()
        self._session = pool.get_session(settings.nebula_user, settings.nebula_password)
        return self._session

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            self._session.release()


def get_nebula_session():
    return NebulaSession()


async def check_nebula_health() -> bool:
    try:
        with get_nebula_session() as session:
            result = session.execute("SHOW HOSTS")
            return result.is_succeeded()
    except Exception as e:
        logger.error("nebula_health_check_failed", error=str(e))
        return False
