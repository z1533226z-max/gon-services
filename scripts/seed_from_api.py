"""
smok95 API를 사용하여 전체 로또 데이터를 DB에 시딩하는 스크립트.

사용법:
    python -m scripts.seed_from_api                 # 전체 시딩 (1~최신)
    python -m scripts.seed_from_api --from 1 --to 100   # 범위 지정
"""

import argparse
import sys
import os

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import test_connection
from app.core.logger import logger
from app.services.lotto_collector import collect_range, collect_latest


def main():
    parser = argparse.ArgumentParser(description="로또 데이터 DB 시딩")
    parser.add_argument("--from", dest="from_round", type=int, default=1, help="시작 회차 (기본: 1)")
    parser.add_argument("--to", dest="to_round", type=int, default=0, help="종료 회차 (기본: 최신)")
    args = parser.parse_args()

    if not test_connection():
        logger.error("DB 연결 실패. DATABASE_URL 환경변수를 확인하세요.")
        sys.exit(1)

    logger.info("DB 연결 성공. 시딩 시작...")

    # 테이블 자동 생성 (공유 마이그레이션 사용)
    from app.core.migrations import run_migrations
    run_migrations()

    if args.to_round > 0:
        # 범위 지정
        result = collect_range(args.from_round, args.to_round)
    else:
        # 전체 시딩 (1~최신)
        result = collect_range(args.from_round, 2000)

    logger.info(f"시딩 완료: {result}")


if __name__ == "__main__":
    main()
