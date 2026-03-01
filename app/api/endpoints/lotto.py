from fastapi import APIRouter, HTTPException, Query
from app.core.database import execute_query, execute_one
from app.core.logger import logger

router = APIRouter()


@router.get("/latest")
async def get_latest():
    """최신 회차 데이터 반환"""
    row = execute_one(
        "SELECT * FROM lotto_results ORDER BY round DESC LIMIT 1"
    )
    if not row:
        raise HTTPException(status_code=404, detail="데이터 없음")
    return _format_result(row)


@router.get("/results")
async def get_results(
    from_round: int = Query(default=1, alias="from", ge=1),
    to_round: int = Query(default=9999, alias="to", ge=1),
):
    """범위 조회 (전체 또는 from~to)"""
    rows = execute_query(
        "SELECT * FROM lotto_results WHERE round >= %s AND round <= %s ORDER BY round ASC",
        (from_round, to_round),
    )
    return [_format_result(r) for r in rows]


@router.get("/round/{round_no}")
async def get_round(round_no: int):
    """특정 회차 조회"""
    row = execute_one(
        "SELECT * FROM lotto_results WHERE round = %s",
        (round_no,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"{round_no}회차 데이터 없음")
    return _format_result(row)


@router.get("/statistics")
async def get_statistics():
    """통계 데이터 반환"""
    total = execute_one("SELECT COUNT(*) as count, MAX(round) as max_round FROM lotto_results")
    if not total or total["count"] == 0:
        raise HTTPException(status_code=404, detail="데이터 없음")

    # 번호별 출현 빈도
    freq_query = """
        SELECT num, COUNT(*) as cnt FROM (
            SELECT num1 as num FROM lotto_results UNION ALL
            SELECT num2 FROM lotto_results UNION ALL
            SELECT num3 FROM lotto_results UNION ALL
            SELECT num4 FROM lotto_results UNION ALL
            SELECT num5 FROM lotto_results UNION ALL
            SELECT num6 FROM lotto_results
        ) t GROUP BY num ORDER BY num
    """
    freq_rows = execute_query(freq_query)

    # 보너스 번호 빈도
    bonus_query = """
        SELECT bonus as num, COUNT(*) as cnt
        FROM lotto_results GROUP BY bonus ORDER BY bonus
    """
    bonus_rows = execute_query(bonus_query)

    return {
        "totalRounds": total["count"],
        "maxRound": total["max_round"],
        "numberFrequency": {row["num"]: row["cnt"] for row in freq_rows},
        "bonusFrequency": {row["num"]: row["cnt"] for row in bonus_rows},
    }


@router.post("/collect")
async def trigger_collect():
    """수동 데이터 수집 트리거 (API Key 인증 필요)"""
    from app.services.lotto_collector import collect_latest

    result = collect_latest()
    return {"status": "ok", "result": result}


def _format_result(row: dict) -> dict:
    """DB 행을 API 응답 포맷으로 변환"""
    return {
        "round": row["round"],
        "drawDate": row["draw_date"].isoformat() if row.get("draw_date") else None,
        "numbers": [row["num1"], row["num2"], row["num3"], row["num4"], row["num5"], row["num6"]],
        "bonusNumber": row["bonus"],
        "prizeMoney": {
            "first": row.get("prize_1st"),
            "firstWinners": row.get("winners_1st"),
        },
    }
