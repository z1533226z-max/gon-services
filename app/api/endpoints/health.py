from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check():
    """시스템 헬스 체크"""
    from app.core.database import test_connection

    db_ok = test_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "service": "gon-services",
        "version": "1.0.0",
    }
