"""DB 마이그레이션 SQL 정의 (단일 소스)"""

from app.core.database import execute_insert
from app.core.logger import logger

MIGRATIONS = [
    """
    CREATE TABLE IF NOT EXISTS lotto_results (
        round       INTEGER PRIMARY KEY,
        draw_date   DATE NOT NULL,
        num1        SMALLINT NOT NULL,
        num2        SMALLINT NOT NULL,
        num3        SMALLINT NOT NULL,
        num4        SMALLINT NOT NULL,
        num5        SMALLINT NOT NULL,
        num6        SMALLINT NOT NULL,
        bonus       SMALLINT NOT NULL,
        prize_1st   BIGINT,
        winners_1st INTEGER,
        prize_2nd   BIGINT,
        winners_2nd INTEGER,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_lotto_draw_date ON lotto_results(draw_date DESC)",
    # 기존 테이블에 2등 컬럼 추가 (이미 있으면 무시)
    "ALTER TABLE lotto_results ADD COLUMN IF NOT EXISTS prize_2nd BIGINT",
    "ALTER TABLE lotto_results ADD COLUMN IF NOT EXISTS winners_2nd INTEGER",
]


def run_migrations():
    """마이그레이션 실행 (멱등). 실패 시 예외를 raise."""
    failed = []
    for sql in MIGRATIONS:
        try:
            execute_insert(sql)
        except Exception as e:
            failed.append(str(e))
            logger.warning(f"마이그레이션 실패: {e}")
    if failed:
        raise RuntimeError(f"마이그레이션 {len(failed)}건 실패: {'; '.join(failed)}")
    logger.info("DB 마이그레이션 완료")
