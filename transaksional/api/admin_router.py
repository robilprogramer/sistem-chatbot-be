from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum

from transaksional.app.config import settings
from transaksional.app.database import get_db_manager,DatabaseManager

router = APIRouter(
    prefix=f"{settings.transactional_prefix}/admin",
    tags=["Admin"]
)



# =============================================================================
# ENUMS & MODELS
# =============================================================================

class RegistrationStatus(str, Enum):
    DRAFT = "draft"
    PENDING_PAYMENT = "pending_payment"
    PAYMENT_UPLOADED = "payment_uploaded"
    PAYMENT_VERIFIED = "payment_verified"
    DOCUMENTS_REVIEW = "documents_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    VERIFIED = "verified"
    REJECTED = "rejected"
    REVISION_NEEDED = "revision_needed"


class UpdateStatusRequest(BaseModel):
    status: RegistrationStatus
    notes: Optional[str] = None
    changed_by: str = "admin"


class UpdateDocumentStatusRequest(BaseModel):
    status: DocumentStatus
    notes: Optional[str] = None


class BulkStatusUpdateRequest(BaseModel):
    registration_numbers: List[str]
    status: RegistrationStatus
    notes: Optional[str] = None
    changed_by: str = "admin"


class RegistrationFilter(BaseModel):
    status: Optional[RegistrationStatus] = None
    user_id: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    search: Optional[str] = None  # Search by name, reg number, etc.
    tingkatan: Optional[str] = None
    sekolah: Optional[str] = None


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)
    sort_by: str = "created_at"
    sort_order: str = "desc"  # asc or desc


# =============================================================================
# DEPENDENCY
# =============================================================================

def get_db() -> DatabaseManager:
    return get_db_manager()


# =============================================================================
# DASHBOARD & STATISTICS
# =============================================================================

@router.get("/dashboard")
async def get_admin_dashboard(db: DatabaseManager = Depends(get_db)):
    """
    Get admin dashboard with overview statistics
    """
    stats = db.get_registration_stats()
    
    # Get additional metrics
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Pending actions count
        cursor.execute("""
            SELECT COUNT(*) as count FROM registrations 
            WHERE status IN ('pending_payment', 'payment_uploaded', 'documents_review')
        """)
        pending_actions = cursor.fetchone()["count"]
        
        # Recent registrations (last 24 hours)
        cursor.execute("""
            SELECT COUNT(*) as count FROM registrations 
            WHERE created_at >= datetime('now', '-1 day')
        """)
        last_24h = cursor.fetchone()["count"]
        
        # Documents pending verification
        cursor.execute("""
            SELECT COUNT(*) as count FROM documents 
            WHERE status = 'uploaded'
        """)
        docs_pending = cursor.fetchone()["count"]
        
        # Registration by tingkatan
        cursor.execute("""
            SELECT 
                json_extract(student_data, '$.tingkatan') as tingkatan,
                COUNT(*) as count
            FROM registrations 
            WHERE status != 'draft' AND student_data IS NOT NULL
            GROUP BY tingkatan
        """)
        by_tingkatan = {row["tingkatan"]: row["count"] for row in cursor.fetchall() if row["tingkatan"]}
        
        # Recent activity (last 10 status changes)
        cursor.execute("""
            SELECT sh.*, r.session_id,
                   json_extract(r.student_data, '$.nama_lengkap') as student_name
            FROM status_history sh
            LEFT JOIN registrations r ON sh.registration_number = r.registration_number
            ORDER BY sh.changed_at DESC
            LIMIT 10
        """)
        recent_activity = [dict(row) for row in cursor.fetchall()]
    
    return {
        "success": True,
        "data": {
            "overview": {
                "total_registrations": stats["total"],
                "today": stats["today"],
                "this_week": stats["this_week"],
                "last_24_hours": last_24h,
                "pending_actions": pending_actions,
                "documents_pending_verification": docs_pending
            },
            "by_status": stats["by_status"],
            "by_tingkatan": by_tingkatan,
            "recent_activity": recent_activity
        }
    }


@router.get("/statistics")
async def get_detailed_statistics(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: DatabaseManager = Depends(get_db)
):
    """
    Get detailed registration statistics with date filters
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Build date filter
        date_filter = ""
        params = []
        if date_from:
            date_filter += " AND DATE(created_at) >= ?"
            params.append(date_from.isoformat())
        if date_to:
            date_filter += " AND DATE(created_at) <= ?"
            params.append(date_to.isoformat())
        
        # Daily registration trend (last 30 days)
        cursor.execute("""
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM registrations
            WHERE created_at >= DATE('now', '-30 days')
            GROUP BY DATE(created_at)
            ORDER BY date
        """)
        daily_trend = [{"date": row["date"], "count": row["count"]} for row in cursor.fetchall()]
        
        # Status distribution
        cursor.execute(f"""
            SELECT status, COUNT(*) as count
            FROM registrations
            WHERE 1=1 {date_filter}
            GROUP BY status
        """, params)
        status_distribution = {row["status"]: row["count"] for row in cursor.fetchall()}
        
        # By sekolah (school)
        cursor.execute(f"""
            SELECT 
                json_extract(student_data, '$.nama_sekolah') as sekolah,
                COUNT(*) as count
            FROM registrations
            WHERE student_data IS NOT NULL {date_filter}
            GROUP BY sekolah
            ORDER BY count DESC
            LIMIT 10
        """, params)
        by_sekolah = [{"sekolah": row["sekolah"], "count": row["count"]} 
                      for row in cursor.fetchall() if row["sekolah"]]
        
        # By program
        cursor.execute(f"""
            SELECT 
                json_extract(student_data, '$.program') as program,
                COUNT(*) as count
            FROM registrations
            WHERE student_data IS NOT NULL {date_filter}
            GROUP BY program
        """, params)
        by_program = {row["program"]: row["count"] for row in cursor.fetchall() if row["program"]}
        
        # Conversion funnel
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status != 'draft' THEN 1 ELSE 0 END) as confirmed,
                SUM(CASE WHEN status IN ('payment_verified', 'documents_review', 'approved') THEN 1 ELSE 0 END) as paid,
                SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved
            FROM registrations
        """)
        funnel_row = cursor.fetchone()
        conversion_funnel = {
            "started": funnel_row["total"],
            "confirmed": funnel_row["confirmed"],
            "paid": funnel_row["paid"],
            "approved": funnel_row["approved"]
        }
        
        # Average completion time (draft to approved)
        cursor.execute("""
            SELECT AVG(
                julianday(
                    (SELECT changed_at FROM status_history 
                     WHERE registration_number = r.registration_number 
                     AND new_status = 'approved' LIMIT 1)
                ) - julianday(r.created_at)
            ) as avg_days
            FROM registrations r
            WHERE status = 'approved'
        """)
        avg_completion = cursor.fetchone()["avg_days"]
    
    return {
        "success": True,
        "data": {
            "daily_trend": daily_trend,
            "status_distribution": status_distribution,
            "by_sekolah": by_sekolah,
            "by_program": by_program,
            "conversion_funnel": conversion_funnel,
            "average_completion_days": round(avg_completion, 1) if avg_completion else None
        }
    }


# =============================================================================
# REGISTRATION MANAGEMENT
# =============================================================================

@router.get("/registrations")
async def list_registrations(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: Optional[RegistrationStatus] = None,
    user_id: Optional[str] = None,
    search: Optional[str] = None,
    tingkatan: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    db: DatabaseManager = Depends(get_db)
):
    """
    List all registrations with filtering and pagination
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Build query
        where_clauses = ["1=1"]
        params = []
        
        if status:
            where_clauses.append("status = ?")
            params.append(status.value)
        
        if user_id:
            where_clauses.append("user_id = ?")
            params.append(user_id)
        
        if search:
            where_clauses.append("""
                (registration_number LIKE ? 
                OR json_extract(student_data, '$.nama_lengkap') LIKE ?
                OR session_id LIKE ?)
            """)
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern, search_pattern])
        
        if tingkatan:
            where_clauses.append("json_extract(student_data, '$.tingkatan') = ?")
            params.append(tingkatan)
        
        if date_from:
            where_clauses.append("DATE(created_at) >= ?")
            params.append(date_from.isoformat())
        
        if date_to:
            where_clauses.append("DATE(created_at) <= ?")
            params.append(date_to.isoformat())
        
        where_sql = " AND ".join(where_clauses)
        
        # Validate sort column
        allowed_sort = ["created_at", "updated_at", "registration_number", "status", "completion_percentage"]
        if sort_by not in allowed_sort:
            sort_by = "created_at"
        sort_order = "DESC" if sort_order.lower() == "desc" else "ASC"
        
        # Get total count
        cursor.execute(f"SELECT COUNT(*) as total FROM registrations WHERE {where_sql}", params)
        total = cursor.fetchone()["total"]
        
        # Get paginated results
        offset = (page - 1) * per_page
        cursor.execute(f"""
            SELECT * FROM registrations 
            WHERE {where_sql}
            ORDER BY {sort_by} {sort_order}
            LIMIT ? OFFSET ?
        """, params + [per_page, offset])
        
        rows = cursor.fetchall()
        
        registrations = []
        for row in rows:
            reg = {
                "id": row["id"],
                "session_id": row["session_id"],
                "user_id": row["user_id"],
                "registration_number": row["registration_number"],
                "status": row["status"],
                "current_step": row["current_step"],
                "completion_percentage": row["completion_percentage"],
                "student_data": _safe_json_loads(row["student_data"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "confirmed_at": row["confirmed_at"]
            }
            registrations.append(reg)
    
    return {
        "success": True,
        "data": {
            "registrations": registrations,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page
            }
        }
    }


@router.get("/registrations/{registration_number}")
async def get_registration_detail(
    registration_number: str,
    db: DatabaseManager = Depends(get_db)
):
    """
    Get detailed registration information
    """
    registration = db.get_registration(registration_number)
    
    if not registration:
        raise HTTPException(status_code=404, detail="Registration not found")
    
    # Get conversation history
    conversation = db.get_conversation_history(registration["session_id"], limit=100)
    
    return {
        "success": True,
        "data": {
            "registration": registration,
            "conversation_history": conversation
        }
    }


@router.put("/registrations/{registration_number}/status")
async def update_registration_status(
    registration_number: str,
    request: UpdateStatusRequest,
    db: DatabaseManager = Depends(get_db)
):
    """
    Update registration status
    """
    # Verify registration exists
    registration = db.get_registration(registration_number)
    if not registration:
        raise HTTPException(status_code=404, detail="Registration not found")
    
    # Validate status transition
    valid_transitions = {
        "draft": ["pending_payment", "cancelled"],
        "pending_payment": ["payment_uploaded", "cancelled"],
        "payment_uploaded": ["payment_verified", "pending_payment", "cancelled"],
        "payment_verified": ["documents_review", "cancelled"],
        "documents_review": ["approved", "rejected", "payment_verified"],
        "approved": [],
        "rejected": ["documents_review"],  # Allow re-review
        "cancelled": []
    }
    
    current_status = registration["status"]
    new_status = request.status.value
    
    if new_status not in valid_transitions.get(current_status, []):
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid status transition from '{current_status}' to '{new_status}'"
        )
    
    success = db.update_registration_status(
        registration_number=registration_number,
        status=new_status,
        notes=request.notes,
        changed_by=request.changed_by
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update status")
    
    return {
        "success": True,
        "message": f"Status updated to {new_status}",
        "data": {
            "registration_number": registration_number,
            "old_status": current_status,
            "new_status": new_status
        }
    }


@router.post("/registrations/bulk-status")
async def bulk_update_status(
    request: BulkStatusUpdateRequest,
    db: DatabaseManager = Depends(get_db)
):
    """
    Update status for multiple registrations
    """
    results = {
        "success": [],
        "failed": []
    }
    
    for reg_number in request.registration_numbers:
        try:
            registration = db.get_registration(reg_number)
            if not registration:
                results["failed"].append({"registration_number": reg_number, "error": "Not found"})
                continue
            
            success = db.update_registration_status(
                registration_number=reg_number,
                status=request.status.value,
                notes=request.notes,
                changed_by=request.changed_by
            )
            
            if success:
                results["success"].append(reg_number)
            else:
                results["failed"].append({"registration_number": reg_number, "error": "Update failed"})
        except Exception as e:
            results["failed"].append({"registration_number": reg_number, "error": str(e)})
    
    return {
        "success": True,
        "data": {
            "updated_count": len(results["success"]),
            "failed_count": len(results["failed"]),
            "results": results
        }
    }


@router.delete("/registrations/{registration_number}")
async def delete_registration(
    registration_number: str,
    db: DatabaseManager = Depends(get_db)
):
    """
    Delete a registration (soft delete - change status to cancelled)
    """
    registration = db.get_registration(registration_number)
    if not registration:
        raise HTTPException(status_code=404, detail="Registration not found")
    
    # Only allow deletion of draft or cancelled
    if registration["status"] not in ["draft", "cancelled"]:
        raise HTTPException(
            status_code=400, 
            detail="Cannot delete registration. Cancel it first."
        )
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM registrations WHERE registration_number = ?",
            (registration_number,)
        )
        cursor.execute(
            "DELETE FROM documents WHERE registration_number = ?",
            (registration_number,)
        )
    
    return {
        "success": True,
        "message": "Registration deleted successfully"
    }


# =============================================================================
# DOCUMENT MANAGEMENT
# =============================================================================

@router.get("/documents")
async def list_documents(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: Optional[DocumentStatus] = None,
    registration_number: Optional[str] = None,
    db: DatabaseManager = Depends(get_db)
):
    """
    List all documents with filtering
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        where_clauses = ["1=1"]
        params = []
        
        if status:
            where_clauses.append("d.status = ?")
            params.append(status.value)
        
        if registration_number:
            where_clauses.append("d.registration_number = ?")
            params.append(registration_number)
        
        where_sql = " AND ".join(where_clauses)
        
        # Get total
        cursor.execute(f"SELECT COUNT(*) as total FROM documents d WHERE {where_sql}", params)
        total = cursor.fetchone()["total"]
        
        # Get documents with registration info
        offset = (page - 1) * per_page
        cursor.execute(f"""
            SELECT d.*, 
                   r.status as registration_status,
                   json_extract(r.student_data, '$.nama_lengkap') as student_name
            FROM documents d
            LEFT JOIN registrations r ON d.registration_number = r.registration_number
            WHERE {where_sql}
            ORDER BY d.uploaded_at DESC
            LIMIT ? OFFSET ?
        """, params + [per_page, offset])
        
        documents = [dict(row) for row in cursor.fetchall()]
    
    return {
        "success": True,
        "data": {
            "documents": documents,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page
            }
        }
    }


@router.get("/documents/pending")
async def get_pending_documents(db: DatabaseManager = Depends(get_db)):
    """
    Get all documents pending verification
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.*, 
                   r.status as registration_status,
                   json_extract(r.student_data, '$.nama_lengkap') as student_name,
                   json_extract(r.student_data, '$.tingkatan') as tingkatan
            FROM documents d
            LEFT JOIN registrations r ON d.registration_number = r.registration_number
            WHERE d.status = 'uploaded'
            ORDER BY d.uploaded_at ASC
        """)
        documents = [dict(row) for row in cursor.fetchall()]
    
    return {
        "success": True,
        "data": {
            "documents": documents,
            "total": len(documents)
        }
    }


@router.put("/documents/{doc_id}/status")
async def update_document_status(
    doc_id: int,
    request: UpdateDocumentStatusRequest,
    db: DatabaseManager = Depends(get_db)
):
    """
    Update document verification status
    """
    success = db.update_document_status(
        doc_id=doc_id,
        status=request.status.value,
        notes=request.notes
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {
        "success": True,
        "message": f"Document status updated to {request.status.value}"
    }


@router.post("/documents/bulk-verify")
async def bulk_verify_documents(
    doc_ids: List[int] = Body(...),
    status: DocumentStatus = Body(DocumentStatus.VERIFIED),
    notes: Optional[str] = Body(None),
    db: DatabaseManager = Depends(get_db)
):
    """
    Verify multiple documents at once
    """
    results = {"success": [], "failed": []}
    
    for doc_id in doc_ids:
        success = db.update_document_status(doc_id, status.value, notes)
        if success:
            results["success"].append(doc_id)
        else:
            results["failed"].append(doc_id)
    
    return {
        "success": True,
        "data": {
            "verified_count": len(results["success"]),
            "failed_count": len(results["failed"]),
            "results": results
        }
    }


# =============================================================================
# USER MANAGEMENT (View registrations by user)
# =============================================================================

@router.get("/users")
async def list_users_with_registrations(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: DatabaseManager = Depends(get_db)
):
    """
    List all users who have registrations
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Get total unique users
        cursor.execute("""
            SELECT COUNT(DISTINCT user_id) as total 
            FROM registrations 
            WHERE user_id IS NOT NULL
        """)
        total = cursor.fetchone()["total"]
        
        # Get users with registration counts
        offset = (page - 1) * per_page
        cursor.execute("""
            SELECT 
                user_id,
                COUNT(*) as registration_count,
                SUM(CASE WHEN status = 'draft' THEN 1 ELSE 0 END) as drafts,
                SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
                SUM(CASE WHEN status NOT IN ('draft', 'approved', 'rejected', 'cancelled') THEN 1 ELSE 0 END) as in_progress,
                MAX(created_at) as last_registration
            FROM registrations
            WHERE user_id IS NOT NULL
            GROUP BY user_id
            ORDER BY last_registration DESC
            LIMIT ? OFFSET ?
        """, (per_page, offset))
        
        users = [dict(row) for row in cursor.fetchall()]
    
    return {
        "success": True,
        "data": {
            "users": users,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page
            }
        }
    }


@router.get("/users/{user_id}/registrations")
async def get_user_registrations(
    user_id: str,
    db: DatabaseManager = Depends(get_db)
):
    """
    Get all registrations for a specific user
    """
    registrations = db.get_registrations_by_user(user_id)
    
    return {
        "success": True,
        "data": {
            "user_id": user_id,
            "registrations": registrations,
            "total": len(registrations)
        }
    }


# =============================================================================
# EXPORT & REPORTS
# =============================================================================

@router.get("/export/registrations")
async def export_registrations(
    status: Optional[RegistrationStatus] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    # format: str = Query("json", regex="^(json|csv)$"),
    format: str = Query("json", pattern="^(json|csv)$"),
    db: DatabaseManager = Depends(get_db)
):
    """
    Export registrations data
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        where_clauses = ["status != 'draft'"]
        params = []
        
        if status:
            where_clauses.append("status = ?")
            params.append(status.value)
        
        if date_from:
            where_clauses.append("DATE(created_at) >= ?")
            params.append(date_from.isoformat())
        
        if date_to:
            where_clauses.append("DATE(created_at) <= ?")
            params.append(date_to.isoformat())
        
        where_sql = " AND ".join(where_clauses)
        
        cursor.execute(f"""
            SELECT 
                registration_number,
                user_id,
                status,
                json_extract(student_data, '$.nama_lengkap') as nama_lengkap,
                json_extract(student_data, '$.nama_sekolah') as nama_sekolah,
                json_extract(student_data, '$.tingkatan') as tingkatan,
                json_extract(student_data, '$.program') as program,
                json_extract(student_data, '$.jenis_kelamin') as jenis_kelamin,
                json_extract(student_data, '$.tempat_lahir') as tempat_lahir,
                json_extract(student_data, '$.tanggal_lahir') as tanggal_lahir,
                created_at,
                confirmed_at,
                updated_at
            FROM registrations
            WHERE {where_sql}
            ORDER BY created_at DESC
        """, params)
        
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]
    
    if format == "csv":
        import csv
        import io
        
        output = io.StringIO()
        if data:
            writer = csv.DictWriter(output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        
        return JSONResponse(
            content={"success": True, "data": output.getvalue()},
            headers={"Content-Disposition": "attachment; filename=registrations.csv"}
        )
    
    return {
        "success": True,
        "data": {
            "registrations": data,
            "total": len(data),
            "exported_at": datetime.now().isoformat()
        }
    }


# =============================================================================
# SYSTEM & MAINTENANCE
# =============================================================================

@router.post("/maintenance/cleanup-drafts")
async def cleanup_expired_drafts(db: DatabaseManager = Depends(get_db)):
    """
    Clean up expired draft registrations
    """
    deleted_count = db.cleanup_expired_drafts()
    
    return {
        "success": True,
        "message": f"Cleaned up {deleted_count} expired drafts"
    }


@router.get("/system/health")
async def system_health(db: DatabaseManager = Depends(get_db)):
    """
    Check system health
    """
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM registrations")
            count = cursor.fetchone()["count"]
        
        return {
            "success": True,
            "status": "healthy",
            "database": "connected",
            "total_registrations": count,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "success": False,
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _safe_json_loads(data: str) -> Optional[Dict]:
    """Safely parse JSON string"""
    if not data:
        return None
    try:
        import json
        return json.loads(data)
    except:
        return None