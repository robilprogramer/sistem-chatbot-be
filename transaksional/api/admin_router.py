from datetime import datetime

from fastapi import APIRouter

from transaksional.app.config import settings
from transaksional.app.database import get_db_manager

router = APIRouter(
    prefix=f"{settings.transactional_prefix}/admin",
    tags=["Admin"]
)


@router.get("/stats")
async def get_stats():
    """Get registration statistics."""
    db = get_db_manager()
    return {
        "statistics": db.get_registration_stats(),
        "timestamp": datetime.now().isoformat()
    }


@router.post("/cleanup")
async def cleanup():
    """Cleanup expired draft registrations."""
    db = get_db_manager()
    drafts_removed = db.cleanup_expired_drafts()
    return {
        "drafts_removed": drafts_removed,
        "message": "Cleanup completed"
    }