import hmac
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import get_settings
from app.api.router import api_router
from app.core.logger import logger
from app.core.database import test_connection, execute_insert
from app.core.scheduler import init_scheduler, shutdown_scheduler


def _run_migrations():
    """자동 DB 마이그레이션 — 테이블 생성 (멱등)"""
    migrations = [
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
            created_at  TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_lotto_draw_date ON lotto_results(draw_date DESC)",
    ]
    for sql in migrations:
        try:
            execute_insert(sql)
        except Exception as e:
            logger.warning(f"마이그레이션 실패 (무시): {e}")
    logger.info("DB 마이그레이션 완료")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("GON-SERVICES 백엔드 시작")

    if test_connection():
        logger.info("DB 연결 성공")
        _run_migrations()
    else:
        logger.warning("DB 연결 실패 -- 환경변수 확인 필요")

    init_scheduler()
    yield

    shutdown_scheduler()
    logger.info("GON-SERVICES 백엔드 종료")


class APIKeyMiddleware(BaseHTTPMiddleware):
    """X-API-Key 헤더 검증 미들웨어. health/GET 요청은 제외."""

    EXEMPT_PATHS = {"/api/v1/health"}
    EXEMPT_METHODS_BY_PREFIX = {
        "/api/v1/lotto": {"GET"},
    }

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()

        # API Key 미설정 시 모든 요청 허용 (개발 모드)
        if not settings.api_key:
            return await call_next(request)

        # 헬스체크, CORS preflight는 제외
        if request.url.path in self.EXEMPT_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        # GET 요청은 인증 없이 허용 (공개 API)
        for prefix, methods in self.EXEMPT_METHODS_BY_PREFIX.items():
            if request.url.path.startswith(prefix) and request.method in methods:
                return await call_next(request)

        api_key = request.headers.get("X-API-Key", "")
        if not api_key or not hmac.compare_digest(api_key, settings.api_key):
            return Response(
                content='{"detail":"Invalid or missing API key"}',
                status_code=403,
                media_type="application/json",
            )

        return await call_next(request)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="GON-SERVICES API",
        description="로또 데이터 자동 수집 및 제공 백엔드",
        version="1.0.0",
        lifespan=lifespan,
    )

    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

    app.add_middleware(APIKeyMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key"],
    )

    app.include_router(api_router, prefix=settings.api_prefix)

    return app


app = create_app()
