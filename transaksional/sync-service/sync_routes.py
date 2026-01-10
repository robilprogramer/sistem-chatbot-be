"""
Sync Routes - API Endpoints untuk Sync Service
===============================================
Endpoints untuk trigger sync manual atau dari admin panel
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional
from pydantic import BaseModel

from app.sync_service import get_sync_service, run_sync, sync_registration

router = APIRouter(prefix="/sync", tags=["sync"])


class SyncRequest(BaseModel):
    registration_number: Optional[str] = None
    session_id: Optional[str] = None


class SyncResponse(BaseModel):
    success: bool
    message: str
    data: dict = None


# =========================================================================
# SYNC ENDPOINTS
# =========================================================================

@router.get("/status")
async def get_sync_status():
    """Get current sync status between SQLite and PostgreSQL"""
    try:
        service = get_sync_service()
        status = service.get_sync_status()
        return {
            "success": True,
            "data": status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/init")
async def init_postgres_tables():
    """Initialize PostgreSQL tables"""
    try:
        service = get_sync_service()
        service.init_postgres_tables()
        return {
            "success": True,
            "message": "PostgreSQL tables initialized"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/all")
async def sync_all_registrations(background_tasks: BackgroundTasks):
    """
    Sync all pending registrations from SQLite to PostgreSQL
    Runs in background to avoid timeout
    """
    try:
        # Run in background
        background_tasks.add_task(run_sync)
        
        return {
            "success": True,
            "message": "Sync started in background. Check /sync/status for progress."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/all/blocking")
async def sync_all_registrations_blocking():
    """
    Sync all pending registrations (blocking - waits for completion)
    Use for small datasets or testing
    """
    try:
        report = run_sync()
        return {
            "success": report.get("success", False),
            "message": f"Synced {report['registrations_synced']} registrations, {report['conversations_synced']} conversations",
            "data": report
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/registration/{registration_number}")
async def sync_single_registration(registration_number: str):
    """Sync specific registration by registration number"""
    try:
        service = get_sync_service()
        service.init_postgres_tables()
        success, message = service.sync_registration(registration_number)
        
        if not success:
            raise HTTPException(status_code=404, detail=message)
        
        return {
            "success": True,
            "message": message,
            "registration_number": registration_number
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/{session_id}")
async def sync_by_session(session_id: str):
    """Sync registration and conversation by session ID"""
    try:
        service = get_sync_service()
        service.init_postgres_tables()
        report = service.sync_single_by_session(session_id)
        
        return {
            "success": report["success"],
            "message": f"Registration: {'✅' if report['registration_synced'] else '❌'}, Conversation: {'✅' if report['conversation_synced'] else '❌'}",
            "data": report
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversation/{session_id}")
async def sync_conversation(session_id: str):
    """Sync specific conversation by session ID"""
    try:
        service = get_sync_service()
        service.init_postgres_tables()
        success, message = service.sync_conversation(session_id)
        
        return {
            "success": success,
            "message": message,
            "session_id": session_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def get_sync_logs():
    """Get recent sync logs"""
    try:
        service = get_sync_service()
        return {
            "success": True,
            "logs": service.sync_log[-50:]  # Last 50 logs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))