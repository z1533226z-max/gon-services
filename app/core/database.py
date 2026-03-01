import threading

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from app.config import get_settings
from app.core.logger import logger

_pool: ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> ThreadedConnectionPool:
    """커넥션 풀 싱글톤 반환 (double-checked locking)"""
    global _pool
    if _pool is not None and not _pool.closed:
        return _pool
    with _pool_lock:
        if _pool is not None and not _pool.closed:
            return _pool
        settings = get_settings()
        _pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=settings.database_url,
            cursor_factory=RealDictCursor,
        )
    return _pool


@contextmanager
def get_db():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def execute_query(query: str, params: tuple | None = None) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description:
                return cur.fetchall()
            return []


def execute_one(query: str, params: tuple | None = None) -> dict | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description:
                return cur.fetchone()
            return None


def execute_insert(query: str, params: tuple | None = None) -> dict | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description:
                return cur.fetchone()
            return None


def test_connection() -> bool:
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return True
    except Exception as e:
        logger.error(f"DB 연결 실패: {e}")
        return False
