from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
from app.core.logger import logger

KST = ZoneInfo("Asia/Seoul")
scheduler = AsyncIOScheduler(timezone=KST)


def _run_sync(func, *args):
    """동기 함수를 스케줄러에서 실행할 래퍼"""
    try:
        func(*args)
    except Exception as e:
        logger.error(f"[Scheduler] {func.__name__} 실행 실패: {e}")


def _job_error_listener(event):
    """스케줄 작업 실패/누락 이벤트 리스너"""
    logger.error(
        f"[Scheduler] 작업 이벤트: job_id={event.job_id}, "
        f"exception={getattr(event, 'exception', None)}"
    )


def init_scheduler():
    from app.services.lotto_collector import collect_latest

    scheduler.add_listener(_job_error_listener, EVENT_JOB_ERROR | EVENT_JOB_MISSED)

    # 토요일 추첨(20:45 KST) 후 자동 수집
    # 1차: 토 21:00 — 추첨 직후 (API 반영 안 됐을 수 있음)
    scheduler.add_job(
        _run_sync,
        CronTrigger(day_of_week="sat", hour=21, minute=0, timezone=KST),
        args=[collect_latest],
        id="lotto_collect_1",
        replace_existing=True,
        max_instances=1,
    )

    # 2차: 토 22:00 — API 반영 확인
    scheduler.add_job(
        _run_sync,
        CronTrigger(day_of_week="sat", hour=22, minute=0, timezone=KST),
        args=[collect_latest],
        id="lotto_collect_2",
        replace_existing=True,
        max_instances=1,
    )

    # 3차: 일 00:00 — 안전 백업
    scheduler.add_job(
        _run_sync,
        CronTrigger(day_of_week="sun", hour=0, minute=0, timezone=KST),
        args=[collect_latest],
        id="lotto_collect_3",
        replace_existing=True,
        max_instances=1,
    )

    # 최종: 일 09:00 — 최종 확인
    scheduler.add_job(
        _run_sync,
        CronTrigger(day_of_week="sun", hour=9, minute=0, timezone=KST),
        args=[collect_latest],
        id="lotto_collect_4",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info(f"스케줄러 시작 (KST) -- {len(scheduler.get_jobs())}개 작업 등록")


def shutdown_scheduler():
    scheduler.shutdown(wait=False)
    logger.info("스케줄러 종료")
