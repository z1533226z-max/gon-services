"""
상금 데이터 수정 스크립트.
divisions[1] → divisions[0]으로 잘못 매핑된 상금 데이터를 수정합니다.

사용법:
    python -m scripts.fix_prize_data
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from app.config import get_settings
from app.core.database import test_connection, execute_query, execute_insert
from app.core.logger import logger


def main():
    if not test_connection():
        logger.error("DB 연결 실패")
        sys.exit(1)

    settings = get_settings()
    rows = execute_query("SELECT round FROM lotto_results ORDER BY round ASC")
    total = len(rows)
    updated = 0

    for i, row in enumerate(rows):
        round_no = row["round"]
        url = f"{settings.lotto_api_url}/{round_no}.json"

        try:
            resp = httpx.get(url, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception as e:
            logger.error(f"API 실패 ({round_no}): {e}")
            continue

        divisions = data.get("divisions", [])
        prize_1st = None
        winners_1st = None
        if len(divisions) > 0 and divisions[0]:
            prize_1st = divisions[0].get("prize")
            winners_1st = divisions[0].get("winners")

        execute_insert(
            "UPDATE lotto_results SET prize_1st = %s, winners_1st = %s WHERE round = %s",
            (prize_1st, winners_1st, round_no),
        )
        updated += 1

        if updated % 100 == 0:
            logger.info(f"진행: {updated}/{total}")

    logger.info(f"완료: {updated}건 업데이트")


if __name__ == "__main__":
    main()
