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
            maxconn=10,
            dsn=settings.database_url,
            cursor_factory=RealDictCursor,
            # TCP keepalive로 stale connection 자동 감지
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
        )
    return _pool


@contextmanager
def get_db():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        # stale connection 감지: closed 상태면 교체
        if conn.closed:
            pool.putconn(conn, close=True)
            conn = pool.getconn()

        yield conn
        conn.commit()
    except psycopg2.OperationalError:
        # DB 연결 끊김 — 커넥션을 풀에서 제거
        try:
            pool.putconn(conn, close=True)
        except Exception:
            pass
        conn = None
        raise
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        if conn is not None:
            try:
                if not conn.closed:
                    pool.putconn(conn)
            except Exception:
                pass


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


def close_pool():
    """커넥션 풀 정리 (shutdown 시 호출)"""
    global _pool
    with _pool_lock:
        if _pool is not None and not _pool.closed:
            _pool.closeall()
            logger.info("DB 커넥션 풀 정리 완료")
            _pool = None
