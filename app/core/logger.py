"""loguru 구조화 로깅 — 콘솔 + 파일"""

import sys
from loguru import logger

logger.remove()

# 콘솔 출력
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="INFO",
)

# 일반 파일 로그
logger.add(
    "logs/gon_services_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="14 days",
    level="DEBUG",
    encoding="utf-8",
)
