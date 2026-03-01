import hmac
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import get_settings
from app.api.router import api_router
from app.core.logger import logger
from app.core.database import test_connection, close_pool
from app.core.scheduler import init_scheduler, shutdown_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("GON-SERVICES 백엔드 시작")
    settings = get_settings()

    # API Key 미설정 경고
    if not settings.api_key:
        logger.warning("API_KEY 미설정 — POST 엔드포인트가 무인증 상태입니다")

    # DB 연결 + 마이그레이션
    if test_connection():
        logger.info("DB 연결 성공")
        try:
            from app.core.migrations import run_migrations
            run_migrations()
        except Exception as e:
            logger.error(f"마이그레이션 실패 — 서버 기동 중단: {e}")
            raise
    else:
        logger.error("DB 연결 실패 — 서버 기동 중단. DATABASE_URL을 확인하세요.")
        raise RuntimeError("DB 연결 실패")

    init_scheduler()
    yield

    shutdown_scheduler()
    close_pool()
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

        # 키 누락 → 401, 키 불일치 → 403
        if not api_key:
            return Response(
                content='{"detail":"API key required"}',
                status_code=401,
                media_type="application/json",
            )
        if not hmac.compare_digest(api_key, settings.api_key):
            return Response(
                content='{"detail":"Invalid API key"}',
                status_code=403,
                media_type="application/json",
            )

        return await call_next(request)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="GON-SERVICES API",
        description="로또 데이터 자동 수집 및 제공 백엔드",
        version="1.1.0",
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
