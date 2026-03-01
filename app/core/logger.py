"""loguru 구조화 로깅 — 콘솔 전용 (PaaS ephemeral FS 호환)"""

import sys
import os
from loguru import logger

logger.remove()

# 콘솔 출력
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="INFO",
)

# 로컬 개발 환경에서만 파일 로그 (logs/ 디렉토리가 있거나 LOG_TO_FILE 설정 시)
if os.path.exists("logs") or os.environ.get("LOG_TO_FILE"):
    logger.add(
        "logs/gon_services_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="14 days",
        level="DEBUG",
        encoding="utf-8",
    )
