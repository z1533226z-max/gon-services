import time
from fastapi import APIRouter, HTTPException, Path, Query
from app.core.database import execute_query, execute_one

router = APIRouter()

# 통계 캐시 (5분 TTL)
_stats_cache: dict | None = None
_stats_cache_ts: float = 0
_STATS_CACHE_TTL = 300


@router.get("/latest")
def get_latest():
    """최신 회차 데이터 반환"""
    row = execute_one(
        "SELECT * FROM lotto_results ORDER BY round DESC LIMIT 1"
    )
    if not row:
        raise HTTPException(status_code=404, detail="데이터 없음")
    return _format_result(row)


@router.get("/results")
def get_results(
    from_round: int = Query(default=1, alias="from", ge=1),
    to_round: int = Query(default=999999, alias="to", ge=1),
    limit: int = Query(default=0, ge=0, le=5000),
    offset: int = Query(default=0, ge=0),
):
    """범위 조회 (전체 또는 from~to). limit=0이면 전체 반환."""
    if limit > 0:
        rows = execute_query(
            "SELECT * FROM lotto_results WHERE round >= %s AND round <= %s ORDER BY round ASC LIMIT %s OFFSET %s",
            (from_round, to_round, limit, offset),
        )
    else:
        rows = execute_query(
            "SELECT * FROM lotto_results WHERE round >= %s AND round <= %s ORDER BY round ASC",
            (from_round, to_round),
        )
    return [_format_result(r) for r in rows]


@router.get("/round/{round_no}")
def get_round(round_no: int = Path(ge=1)):
    """특정 회차 조회"""
    row = execute_one(
        "SELECT * FROM lotto_results WHERE round = %s",
        (round_no,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"{round_no}회차 데이터 없음")
    return _format_result(row)


@router.get("/statistics")
def get_statistics():
    """통계 데이터 반환 (5분 캐시)"""
    global _stats_cache, _stats_cache_ts

    now = time.time()
    if _stats_cache and (now - _stats_cache_ts) < _STATS_CACHE_TTL:
        return _stats_cache

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

    result = {
        "totalRounds": total["count"],
        "maxRound": total["max_round"],
        "numberFrequency": {row["num"]: row["cnt"] for row in freq_rows},
        "bonusFrequency": {row["num"]: row["cnt"] for row in bonus_rows},
    }

    _stats_cache = result
    _stats_cache_ts = now
    return result


@router.post("/collect")
def trigger_collect():
    """수동 데이터 수집 트리거 (API Key 인증 필요)"""
    from app.services.lotto_collector import collect_latest

    try:
        result = collect_latest()
        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"수집 실패: {e}")


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
            "second": row.get("prize_2nd"),
            "secondWinners": row.get("winners_2nd"),
        },
    }
