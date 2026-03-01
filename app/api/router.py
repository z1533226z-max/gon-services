from fastapi import APIRouter
from app.api.endpoints import health, lotto

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(lotto.router, prefix="/lotto", tags=["lotto"])
