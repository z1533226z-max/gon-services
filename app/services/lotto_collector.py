"""외부 API에서 로또 당첨번호를 수집하여 DB에 저장하는 서비스"""

import httpx
from app.config import get_settings
from app.core.database import execute_one, execute_insert
from app.core.logger import logger


def collect_latest() -> str:
    """최신 회차 데이터를 수집하여 DB에 저장 (멱등)"""
    settings = get_settings()

    # 1. DB의 마지막 회차 확인
    last = execute_one("SELECT MAX(round) as max_round FROM lotto_results")
    last_round = last["max_round"] if last and last["max_round"] else 0

    # 2. smok95 API에서 최신 회차부터 순차 수집
    new_count = 0
    current = last_round + 1

    while True:
        data = _fetch_round(settings.lotto_api_url, current)
        if not data:
            break

        _insert_round(data)
        new_count += 1
        logger.info(f"[Collector] {current}회차 수집 완료")
        current += 1

    if new_count == 0:
        logger.info(f"[Collector] 새 데이터 없음 (마지막: {last_round}회)")
        return f"no_new_data (last: {last_round})"

    logger.info(f"[Collector] {new_count}개 회차 수집 완료 ({last_round + 1}~{current - 1})")
    return f"collected {new_count} rounds ({last_round + 1}~{current - 1})"


def collect_range(start: int, end: int) -> str:
    """특정 범위의 회차를 수집 (시딩용)"""
    settings = get_settings()
    collected = 0
    skipped = 0

    for round_no in range(start, end + 1):
        # 이미 존재하면 스킵
        existing = execute_one(
            "SELECT round FROM lotto_results WHERE round = %s",
            (round_no,),
        )
        if existing:
            skipped += 1
            continue

        data = _fetch_round(settings.lotto_api_url, round_no)
        if not data:
            logger.warning(f"[Collector] {round_no}회차 데이터 없음 (API)")
            continue

        _insert_round(data)
        collected += 1

        if collected % 100 == 0:
            logger.info(f"[Collector] 진행: {collected}개 수집, {skipped}개 스킵")

    logger.info(f"[Collector] 범위 수집 완료: {collected}개 수집, {skipped}개 스킵")
    return f"collected={collected}, skipped={skipped}"


def _fetch_round(base_url: str, round_no: int) -> dict | None:
    """smok95 API에서 특정 회차 데이터 조회"""
    url = f"{base_url}/{round_no}.json"
    try:
        resp = httpx.get(url, timeout=10)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError:
        return None
    except Exception as e:
        logger.error(f"[Collector] API 요청 실패 ({round_no}): {e}")
        return None


def _insert_round(data: dict) -> None:
    """API 응답 데이터를 DB에 INSERT

    smok95 API 응답 예시:
    {
        "draw_no": 1,
        "numbers": [10, 23, 29, 33, 37, 40],
        "bonus_no": 16,
        "date": "2002-12-07T00:00:00Z",
        "divisions": [{}, {"prize": 143934100, "winners": 1}, ...],
        "total_sales_amount": 3681782000
    }
    """
    round_no = data.get("draw_no")
    draw_date = data.get("date", "")[:10]  # "2002-12-07T00:00:00Z" → "2002-12-07"
    numbers = data.get("numbers", [])
    bonus = data.get("bonus_no")

    # 1등 상금/당첨자 — divisions[1] (index 0은 빈 객체)
    divisions = data.get("divisions", [])
    prize_1st = None
    winners_1st = None
    if len(divisions) > 1:
        prize_1st = divisions[1].get("prize")
        winners_1st = divisions[1].get("winners")

    if not round_no or len(numbers) < 6:
        logger.warning(f"[Collector] 불완전한 데이터 스킵: {data}")
        return

    execute_insert(
        """
        INSERT INTO lotto_results (round, draw_date, num1, num2, num3, num4, num5, num6, bonus, prize_1st, winners_1st)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (round) DO NOTHING
        """,
        (
            round_no, draw_date,
            numbers[0], numbers[1], numbers[2], numbers[3], numbers[4], numbers[5],
            bonus, prize_1st, winners_1st,
        ),
    )
