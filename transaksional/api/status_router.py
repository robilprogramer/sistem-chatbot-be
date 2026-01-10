from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Form
from pydantic import BaseModel

from transaksional.app.config import settings
from transaksional.app.database import get_db_manager

router = APIRouter(
    prefix=settings.transactional_prefix,
    tags=["Status & Tracking"]
)


class StatusResponse(BaseModel):
    registration_number: str
    status: str
    student_data: Dict[str, Any]
    documents: List[Dict[str, Any]]
    status_history: List[Dict[str, Any]]
    created_at: str
    updated_at: str


# Status configuration constant
STATUS_CONFIG = {
    "draft": {"label": "Draft", "color": "gray", "icon": "📝", "progress": 10},
    "pending_payment": {"label": "Menunggu Pembayaran", "color": "yellow", "icon": "⏳", "progress": 30},
    "payment_uploaded": {"label": "Bukti Pembayaran Diterima", "color": "blue", "icon": "📤", "progress": 50},
    "payment_verified": {"label": "Pembayaran Terverifikasi", "color": "green", "icon": "✅", "progress": 70},
    "documents_review": {"label": "Dokumen Direview", "color": "purple", "icon": "📋", "progress": 85},
    "approved": {"label": "Disetujui", "color": "emerald", "icon": "🎉", "progress": 100},
    "rejected": {"label": "Ditolak", "color": "red", "icon": "❌", "progress": 0}
}

VALID_STATUSES = list(STATUS_CONFIG.keys())


@router.get("/status/{registration_number}", response_model=StatusResponse)
async def get_status(registration_number: str):
    """Get registration status by registration number."""
    db = get_db_manager()
    reg_data = db.get_registration(registration_number)
    if not reg_data:
        raise HTTPException(status_code=404, detail="Registration not found")
    
    return StatusResponse(
        registration_number=registration_number,
        status=reg_data.get("status", "unknown"),
        student_data=reg_data.get("student_data", {}),
        documents=reg_data.get("documents", []),
        status_history=reg_data.get("status_history", []),
        created_at=reg_data.get("created_at", ""),
        updated_at=reg_data.get("updated_at", "")
    )


@router.put("/status/{registration_number}")
async def update_status(
    registration_number: str,
    status: str = Form(...),
    notes: Optional[str] = Form(None)
):
    """Update registration status."""
    if status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Valid statuses: {VALID_STATUSES}"
        )
    
    db = get_db_manager()
    if not db.update_registration_status(registration_number, status, notes, "admin"):
        raise HTTPException(status_code=404, detail="Registration not found")
    
    return {
        "registration_number": registration_number,
        "status": status,
        "message": "Updated"
    }


@router.get("/tracking/{registration_number}")
async def get_tracking(registration_number: str):
    """Get detailed tracking information for a registration."""
    db = get_db_manager()
    reg_data = db.get_registration(registration_number)
    if not reg_data:
        raise HTTPException(status_code=404, detail="Registration not found")
    
    current_status = reg_data.get("status", "pending_payment")
    status_info = STATUS_CONFIG.get(current_status, STATUS_CONFIG["pending_payment"])
    
    timeline = []
    for h in reg_data.get("status_history", []):
        status_key = h.get("new_status")
        config = STATUS_CONFIG.get(status_key, {})
        timeline.append({
            "status": status_key,
            "label": config.get("label", ""),
            "icon": config.get("icon", ""),
            "timestamp": h.get("changed_at"),
            "notes": h.get("notes")
        })
    
    documents = []
    for d in reg_data.get("documents", []):
        doc_status = d.get("status")
        documents.append({
            "field_name": d.get("field_name"),
            "status": doc_status,
            "status_icon": "✅" if doc_status == "verified" else "📤"
        })
    
    return {
        "registration_number": registration_number,
        "student_data": reg_data.get("student_data", {}),
        "current_status": {"status": current_status, **status_info},
        "documents": documents,
        "timeline": timeline,
        "created_at": reg_data.get("created_at"),
        "updated_at": reg_data.get("updated_at")
    }