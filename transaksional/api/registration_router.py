"""
Registration Router - User & Admin Views
=========================================
Complete CRUD for registrations and documents with role-based access.

- User: Can only see/manage their own registrations
- Admin: Can see all registrations with full management capabilities
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Body, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum
import json

from transaksional.app.config import settings
from transaksional.app.database import get_db_manager, DatabaseManager


# =============================================================================
# ROUTER SETUP
# =============================================================================

router = APIRouter(
    prefix=f"{settings.transactional_prefix}",
    tags=["Registrations"]
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


# Request Models
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


class BulkDocumentVerifyRequest(BaseModel):
    document_ids: List[int]
    status: DocumentStatus = DocumentStatus.VERIFIED
    notes: Optional[str] = None


# Response Models
class RegistrationSummary(BaseModel):
    registration_number: Optional[str]
    session_id: str
    user_id: Optional[str]
    status: str
    current_step: Optional[str]
    completion_percentage: float
    student_name: Optional[str]
    tingkatan: Optional[str]
    sekolah: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]


class PaginationInfo(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int


# =============================================================================
# DEPENDENCY
# =============================================================================

def get_db() -> DatabaseManager:
    return get_db_manager()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _safe_json_loads(data) -> Optional[Dict]:
    """Safely parse JSON string or return dict as-is"""
    if data is None:
        return None
    if isinstance(data, dict):
        return data
    try:
        return json.loads(data)
    except:
        return None


def _extract_student_info(student_data: Dict) -> Dict:
    """Extract commonly used student info"""
    if not student_data:
        return {}
    return {
        "nama_lengkap": student_data.get("nama_lengkap"),
        "tingkatan": student_data.get("tingkatan"),
        "nama_sekolah": student_data.get("nama_sekolah"),
        "program": student_data.get("program"),
        "jenis_kelamin": student_data.get("jenis_kelamin"),
        "tempat_lahir": student_data.get("tempat_lahir"),
        "tanggal_lahir": student_data.get("tanggal_lahir"),
    }


# =============================================================================
# USER ENDPOINTS - Only own registrations
# =============================================================================

@router.get("/user/{user_id}/registrations")
async def get_user_registrations(
    user_id: str = Path(..., description="User ID"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=50, description="Items per page"),
    status: Optional[RegistrationStatus] = Query(None, description="Filter by status"),
    sort_by: str = Query("updated_at", description="Sort field"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
    db: DatabaseManager = Depends(get_db)
):
    """
    [USER] Get all registrations for a specific user.
    
    User can only access their own registrations.
    """
    with db.get_connection() as conn:
        from psycopg2.extras import RealDictCursor
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Build query
        where_clauses = ["user_id = %s"]
        params = [user_id]
        
        if status:
            where_clauses.append("status = %s")
            params.append(status.value)
        
        where_sql = " AND ".join(where_clauses)
        
        # Validate sort column
        allowed_sort = ["created_at", "updated_at", "status", "completion_percentage"]
        if sort_by not in allowed_sort:
            sort_by = "updated_at"
        sort_direction = "DESC" if sort_order.lower() == "desc" else "ASC"
        
        # Get total count
        cursor.execute(f"SELECT COUNT(*) as total FROM registrations WHERE {where_sql}", params)
        total = cursor.fetchone()["total"]
        
        # Get paginated results
        offset = (page - 1) * per_page
        cursor.execute(f"""
            SELECT 
                id, session_id, user_id, registration_number, status,
                current_step, completion_percentage, student_data,
                created_at, updated_at, confirmed_at
            FROM registrations 
            WHERE {where_sql}
            ORDER BY {sort_by} {sort_direction}
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])
        
        rows = cursor.fetchall()
        
        registrations = []
        for row in rows:
            student_data = _safe_json_loads(row["student_data"])
            registrations.append({
                "id": row["id"],
                "session_id": row["session_id"],
                "registration_number": row["registration_number"],
                "status": row["status"],
                "current_step": row["current_step"],
                "completion_percentage": row["completion_percentage"],
                "student_info": _extract_student_info(student_data),
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                "confirmed_at": row["confirmed_at"].isoformat() if row["confirmed_at"] else None,
            })
    
    return {
        "success": True,
        "data": {
            "registrations": registrations,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page if total > 0 else 0
            }
        }
    }


@router.get("/user/{user_id}/registrations/{registration_number}")
async def get_user_registration_detail(
    user_id: str = Path(..., description="User ID"),
    registration_number: str = Path(..., description="Registration number"),
    db: DatabaseManager = Depends(get_db)
):
    """
    [USER] Get detailed registration info.
    
    User can only view their own registration.
    """
    registration = db.get_registration(registration_number)
    
    if not registration:
        raise HTTPException(status_code=404, detail="Pendaftaran tidak ditemukan")
    
    # Verify ownership
    if registration.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Anda tidak memiliki akses ke pendaftaran ini")
    
    # Get documents
    documents = db.get_documents(registration_number=registration_number)
    
    return {
        "success": True,
        "data": {
            "registration": {
                "registration_number": registration["registration_number"],
                "session_id": registration["session_id"],
                "status": registration["status"],
                "completion_percentage": registration["completion_percentage"],
                "student_data": registration.get("student_data", {}),
                "created_at": registration["created_at"],
                "updated_at": registration["updated_at"],
                "confirmed_at": registration.get("confirmed_at"),
            },
            "documents": documents,
            "status_history": registration.get("status_history", [])
        }
    }


@router.get("/user/{user_id}/documents")
async def get_user_documents(
    user_id: str = Path(..., description="User ID"),
    registration_number: Optional[str] = Query(None, description="Filter by registration"),
    status: Optional[DocumentStatus] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    db: DatabaseManager = Depends(get_db)
):
    """
    [USER] Get all documents for user's registrations.
    """
    with db.get_connection() as conn:
        from psycopg2.extras import RealDictCursor
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Build query - join with registrations to verify ownership
        where_clauses = ["r.user_id = %s"]
        params = [user_id]
        
        if registration_number:
            where_clauses.append("d.registration_number = %s")
            params.append(registration_number)
        
        if status:
            where_clauses.append("d.status = %s")
            params.append(status.value)
        
        where_sql = " AND ".join(where_clauses)
        
        # Get total
        cursor.execute(f"""
            SELECT COUNT(*) as total 
            FROM registration_documents d
            JOIN registrations r ON d.session_id = r.session_id
            WHERE {where_sql}
        """, params)
        total = cursor.fetchone()["total"]
        
        # Get documents
        offset = (page - 1) * per_page
        cursor.execute(f"""
            SELECT 
                d.id, d.session_id, d.registration_number, d.field_name,
                d.file_name, d.file_path, d.file_size, d.file_type,
                d.status, d.uploaded_at, d.verified_at, d.notes
            FROM registration_documents d
            JOIN registrations r ON d.session_id = r.session_id
            WHERE {where_sql}
            ORDER BY d.uploaded_at DESC
            LIMIT %s OFFSET %s
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
                "total_pages": (total + per_page - 1) // per_page if total > 0 else 0
            }
        }
    }


@router.get("/user/{user_id}/stats")
async def get_user_registration_stats(
    user_id: str = Path(..., description="User ID"),
    db: DatabaseManager = Depends(get_db)
):
    """
    [USER] Get registration statistics for a user.
    """
    with db.get_connection() as conn:
        from psycopg2.extras import RealDictCursor
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Status counts
        cursor.execute("""
            SELECT status, COUNT(*) as count 
            FROM registrations 
            WHERE user_id = %s
            GROUP BY status
        """, (user_id,))
        by_status = {row["status"]: row["count"] for row in cursor.fetchall()}
        
        # Total registrations
        cursor.execute("""
            SELECT COUNT(*) as total FROM registrations WHERE user_id = %s
        """, (user_id,))
        total = cursor.fetchone()["total"]
        
        # Documents count
        cursor.execute("""
            SELECT COUNT(*) as total 
            FROM registration_documents d
            JOIN registrations r ON d.session_id = r.session_id
            WHERE r.user_id = %s
        """, (user_id,))
        total_documents = cursor.fetchone()["total"]
        
        # Recent activity
        cursor.execute("""
            SELECT registration_number, status, updated_at
            FROM registrations
            WHERE user_id = %s
            ORDER BY updated_at DESC
            LIMIT 5
        """, (user_id,))
        recent = [dict(row) for row in cursor.fetchall()]
    
    return {
        "success": True,
        "data": {
            "total_registrations": total,
            "total_documents": total_documents,
            "by_status": by_status,
            "recent_activity": recent
        }
    }


# =============================================================================
# ADMIN ENDPOINTS - Full access
# =============================================================================

@router.get("/admin/registrations")
async def admin_list_registrations(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: Optional[RegistrationStatus] = Query(None, description="Filter by status"),
    user_id: Optional[str] = Query(None, description="Filter by user"),
    search: Optional[str] = Query(None, description="Search by name/reg number"),
    tingkatan: Optional[str] = Query(None, description="Filter by tingkatan (TK/SD/SMP/SMA)"),
    sekolah: Optional[str] = Query(None, description="Filter by school name"),
    date_from: Optional[date] = Query(None, description="Filter from date"),
    date_to: Optional[date] = Query(None, description="Filter to date"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: DatabaseManager = Depends(get_db)
):
    """
    [ADMIN] List all registrations with comprehensive filtering.
    """
    with db.get_connection() as conn:
        from psycopg2.extras import RealDictCursor
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Build query
        where_clauses = ["1=1"]
        params = []
        
        if status:
            where_clauses.append("status = %s")
            params.append(status.value)
        
        if user_id:
            where_clauses.append("user_id = %s")
            params.append(user_id)
        
        if search:
            where_clauses.append("""
                (registration_number ILIKE %s 
                OR student_data->>'nama_lengkap' ILIKE %s
                OR session_id ILIKE %s)
            """)
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern, search_pattern])
        
        if tingkatan:
            where_clauses.append("student_data->>'tingkatan' ILIKE %s")
            params.append(f"%{tingkatan}%")
        
        if sekolah:
            where_clauses.append("student_data->>'nama_sekolah' ILIKE %s")
            params.append(f"%{sekolah}%")
        
        if date_from:
            where_clauses.append("DATE(created_at) >= %s")
            params.append(date_from)
        
        if date_to:
            where_clauses.append("DATE(created_at) <= %s")
            params.append(date_to)
        
        where_sql = " AND ".join(where_clauses)
        
        # Validate sort column
        allowed_sort = ["created_at", "updated_at", "registration_number", "status", "completion_percentage"]
        if sort_by not in allowed_sort:
            sort_by = "created_at"
        sort_direction = "DESC" if sort_order.lower() == "desc" else "ASC"
        
        # Get total count
        cursor.execute(f"SELECT COUNT(*) as total FROM registrations WHERE {where_sql}", params if params else None)
        total = cursor.fetchone()["total"]
        
        # Get paginated results
        offset = (page - 1) * per_page
        cursor.execute(f"""
            SELECT 
                id, session_id, user_id, registration_number, status,
                current_step, completion_percentage, student_data,
                created_at, updated_at, confirmed_at
            FROM registrations 
            WHERE {where_sql}
            ORDER BY {sort_by} {sort_direction}
            LIMIT %s OFFSET %s
        """, (params if params else []) + [per_page, offset])
        
        rows = cursor.fetchall()
        
        registrations = []
        for row in rows:
            student_data = _safe_json_loads(row["student_data"])
            registrations.append({
                "id": row["id"],
                "session_id": row["session_id"],
                "user_id": row["user_id"],
                "registration_number": row["registration_number"],
                "status": row["status"],
                "current_step": row["current_step"],
                "completion_percentage": row["completion_percentage"],
                "student_info": _extract_student_info(student_data),
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                "confirmed_at": row["confirmed_at"].isoformat() if row["confirmed_at"] else None,
            })
    
    return {
        "success": True,
        "data": {
            "registrations": registrations,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page if total > 0 else 0
            },
            "filters_applied": {
                "status": status.value if status else None,
                "user_id": user_id,
                "search": search,
                "tingkatan": tingkatan,
                "sekolah": sekolah,
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
            }
        }
    }


@router.get("/admin/registrations/{registration_number}")
async def admin_get_registration_detail(
    registration_number: str = Path(..., description="Registration number"),
    db: DatabaseManager = Depends(get_db)
):
    """
    [ADMIN] Get detailed registration info with full data.
    """
    registration = db.get_registration(registration_number)
    
    if not registration:
        raise HTTPException(status_code=404, detail="Pendaftaran tidak ditemukan")
    
    # Get conversation history
    conversation = db.get_conversation_history(registration["session_id"], limit=50)
    
    return {
        "success": True,
        "data": {
            "registration": registration,
            "conversation_history": conversation
        }
    }


@router.put("/admin/registrations/{registration_number}/status")
async def admin_update_registration_status(
    registration_number: str = Path(..., description="Registration number"),
    request: UpdateStatusRequest = Body(...),
    db: DatabaseManager = Depends(get_db)
):
    """
    [ADMIN] Update registration status with validation.
    """
    registration = db.get_registration(registration_number)
    if not registration:
        raise HTTPException(status_code=404, detail="Pendaftaran tidak ditemukan")
    
    # Status transition rules
    valid_transitions = {
        "draft": ["pending_payment", "cancelled"],
        "pending_payment": ["payment_uploaded", "cancelled"],
        "payment_uploaded": ["payment_verified", "pending_payment", "cancelled"],
        "payment_verified": ["documents_review", "cancelled"],
        "documents_review": ["approved", "rejected", "payment_verified"],
        "approved": [],
        "rejected": ["documents_review"],
        "cancelled": []
    }
    
    current_status = registration["status"]
    new_status = request.status.value
    
    if new_status not in valid_transitions.get(current_status, []):
        raise HTTPException(
            status_code=400, 
            detail=f"Transisi status tidak valid: '{current_status}' → '{new_status}'"
        )
    
    success = db.update_registration_status(
        registration_number=registration_number,
        status=new_status,
        notes=request.notes,
        changed_by=request.changed_by
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Gagal mengupdate status")
    
    return {
        "success": True,
        "message": f"Status berhasil diupdate ke '{new_status}'",
        "data": {
            "registration_number": registration_number,
            "old_status": current_status,
            "new_status": new_status
        }
    }


@router.post("/admin/registrations/bulk-status")
async def admin_bulk_update_status(
    request: BulkStatusUpdateRequest = Body(...),
    db: DatabaseManager = Depends(get_db)
):
    """
    [ADMIN] Update status for multiple registrations.
    """
    results = {"success": [], "failed": []}
    
    for reg_number in request.registration_numbers:
        try:
            registration = db.get_registration(reg_number)
            if not registration:
                results["failed"].append({
                    "registration_number": reg_number, 
                    "error": "Tidak ditemukan"
                })
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
                results["failed"].append({
                    "registration_number": reg_number, 
                    "error": "Gagal update"
                })
        except Exception as e:
            results["failed"].append({
                "registration_number": reg_number, 
                "error": str(e)
            })
    
    return {
        "success": True,
        "data": {
            "updated_count": len(results["success"]),
            "failed_count": len(results["failed"]),
            "results": results
        }
    }


@router.delete("/admin/registrations/{registration_number}")
async def admin_delete_registration(
    registration_number: str = Path(..., description="Registration number"),
    db: DatabaseManager = Depends(get_db)
):
    """
    [ADMIN] Delete a registration (only draft/cancelled).
    """
    registration = db.get_registration(registration_number)
    if not registration:
        raise HTTPException(status_code=404, detail="Pendaftaran tidak ditemukan")
    
    if registration["status"] not in ["draft", "cancelled"]:
        raise HTTPException(
            status_code=400, 
            detail="Hanya pendaftaran dengan status 'draft' atau 'cancelled' yang bisa dihapus"
        )
    
    with db.get_connection() as conn:
        from psycopg2.extras import RealDictCursor
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Delete documents first
        cursor.execute(
            "DELETE FROM registration_documents WHERE registration_number = %s",
            (registration_number,)
        )
        
        # Delete registration
        cursor.execute(
            "DELETE FROM registrations WHERE registration_number = %s",
            (registration_number,)
        )
    
    return {
        "success": True,
        "message": "Pendaftaran berhasil dihapus"
    }


# =============================================================================
# ADMIN - DOCUMENTS MANAGEMENT
# =============================================================================

@router.get("/admin/documents")
async def admin_list_documents(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: Optional[DocumentStatus] = Query(None),
    registration_number: Optional[str] = Query(None),
    field_name: Optional[str] = Query(None, description="Filter by document type"),
    user_id: Optional[str] = Query(None),
    db: DatabaseManager = Depends(get_db)
):
    """
    [ADMIN] List all documents with filtering.
    """
    with db.get_connection() as conn:
        from psycopg2.extras import RealDictCursor
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        where_clauses = ["1=1"]
        params = []
        
        if status:
            where_clauses.append("d.status = %s")
            params.append(status.value)
        
        if registration_number:
            where_clauses.append("d.registration_number = %s")
            params.append(registration_number)
        
        if field_name:
            where_clauses.append("d.field_name = %s")
            params.append(field_name)
        
        if user_id:
            where_clauses.append("r.user_id = %s")
            params.append(user_id)
        
        where_sql = " AND ".join(where_clauses)
        
        # Get total
        cursor.execute(f"""
            SELECT COUNT(*) as total 
            FROM registration_documents d
            LEFT JOIN registrations r ON d.session_id = r.session_id
            WHERE {where_sql}
        """, params if params else None)
        total = cursor.fetchone()["total"]
        
        # Get documents with registration info
        offset = (page - 1) * per_page
        cursor.execute(f"""
            SELECT 
                d.id, d.session_id, d.registration_number, d.field_name,
                d.file_name, d.file_path, d.file_size, d.file_type,
                d.status, d.uploaded_at, d.verified_at, d.notes,
                r.user_id,
                r.status as registration_status,
                r.student_data->>'nama_lengkap' as student_name
            FROM registration_documents d
            LEFT JOIN registrations r ON d.session_id = r.session_id
            WHERE {where_sql}
            ORDER BY d.uploaded_at DESC
            LIMIT %s OFFSET %s
        """, (params if params else []) + [per_page, offset])
        
        documents = [dict(row) for row in cursor.fetchall()]
    
    return {
        "success": True,
        "data": {
            "documents": documents,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page if total > 0 else 0
            }
        }
    }


@router.get("/admin/documents/pending")
async def admin_get_pending_documents(
    db: DatabaseManager = Depends(get_db)
):
    """
    [ADMIN] Get all documents pending verification.
    """
    with db.get_connection() as conn:
        from psycopg2.extras import RealDictCursor
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT 
                d.id, d.session_id, d.registration_number, d.field_name,
                d.file_name, d.file_path, d.file_size, d.file_type,
                d.status, d.uploaded_at, d.notes,
                r.user_id,
                r.status as registration_status,
                r.student_data->>'nama_lengkap' as student_name,
                r.student_data->>'tingkatan' as tingkatan
            FROM registration_documents d
            LEFT JOIN registrations r ON d.session_id = r.session_id
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


@router.put("/admin/documents/{doc_id}/status")
async def admin_update_document_status(
    doc_id: int = Path(..., description="Document ID"),
    request: UpdateDocumentStatusRequest = Body(...),
    db: DatabaseManager = Depends(get_db)
):
    """
    [ADMIN] Update document verification status.
    """
    success = db.update_document_status(
        doc_id=doc_id,
        status=request.status.value,
        notes=request.notes
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    
    return {
        "success": True,
        "message": f"Status dokumen diupdate ke '{request.status.value}'"
    }


@router.post("/admin/documents/bulk-verify")
async def admin_bulk_verify_documents(
    request: BulkDocumentVerifyRequest = Body(...),
    db: DatabaseManager = Depends(get_db)
):
    """
    [ADMIN] Verify multiple documents at once.
    """
    results = {"success": [], "failed": []}
    
    for doc_id in request.document_ids:
        success = db.update_document_status(doc_id, request.status.value, request.notes)
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
# ADMIN - STATISTICS & DASHBOARD
# =============================================================================

@router.get("/admin/stats/overview")
async def admin_get_overview_stats(
    db: DatabaseManager = Depends(get_db)
):
    """
    [ADMIN] Get overview statistics for dashboard.
    """
    with db.get_connection() as conn:
        from psycopg2.extras import RealDictCursor
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Status distribution
        cursor.execute("""
            SELECT status, COUNT(*) as count 
            FROM registrations 
            GROUP BY status
        """)
        by_status = {row["status"]: row["count"] for row in cursor.fetchall()}
        
        # Today's registrations
        cursor.execute("""
            SELECT COUNT(*) as count FROM registrations 
            WHERE DATE(created_at) = CURRENT_DATE
        """)
        today = cursor.fetchone()["count"]
        
        # This week
        cursor.execute("""
            SELECT COUNT(*) as count FROM registrations 
            WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
        """)
        this_week = cursor.fetchone()["count"]
        
        # Pending actions
        cursor.execute("""
            SELECT COUNT(*) as count FROM registrations 
            WHERE status IN ('pending_payment', 'payment_uploaded', 'documents_review')
        """)
        pending_actions = cursor.fetchone()["count"]
        
        # Documents pending verification
        cursor.execute("""
            SELECT COUNT(*) as count FROM registration_documents 
            WHERE status = 'uploaded'
        """)
        docs_pending = cursor.fetchone()["count"]
        
        # By tingkatan
        cursor.execute("""
            SELECT 
                student_data->>'tingkatan' as tingkatan,
                COUNT(*) as count
            FROM registrations 
            WHERE status != 'draft' AND student_data IS NOT NULL
            GROUP BY student_data->>'tingkatan'
        """)
        by_tingkatan = {row["tingkatan"]: row["count"] for row in cursor.fetchall() if row["tingkatan"]}
        
        # By sekolah (top 10)
        cursor.execute("""
            SELECT 
                student_data->>'nama_sekolah' as sekolah,
                COUNT(*) as count
            FROM registrations 
            WHERE status != 'draft' AND student_data IS NOT NULL
            GROUP BY student_data->>'nama_sekolah'
            ORDER BY count DESC
            LIMIT 10
        """)
        by_sekolah = [{"sekolah": row["sekolah"], "count": row["count"]} 
                      for row in cursor.fetchall() if row["sekolah"]]
        
        # Total
        total = sum(by_status.values()) if by_status else 0
    
    return {
        "success": True,
        "data": {
            "overview": {
                "total_registrations": total,
                "today": today,
                "this_week": this_week,
                "pending_actions": pending_actions,
                "documents_pending_verification": docs_pending
            },
            "by_status": by_status,
            "by_tingkatan": by_tingkatan,
            "by_sekolah": by_sekolah
        }
    }


@router.get("/admin/stats/daily-trend")
async def admin_get_daily_trend(
    days: int = Query(30, ge=7, le=90, description="Number of days"),
    db: DatabaseManager = Depends(get_db)
):
    """
    [ADMIN] Get daily registration trend.
    """
    with db.get_connection() as conn:
        from psycopg2.extras import RealDictCursor
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM registrations
            WHERE created_at >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY DATE(created_at)
            ORDER BY date
        """, (days,))
        
        trend = [{"date": row["date"].isoformat() if row["date"] else None, "count": row["count"]} 
                 for row in cursor.fetchall()]
    
    return {
        "success": True,
        "data": {
            "trend": trend,
            "days": days
        }
    }


@router.get("/admin/stats/conversion-funnel")
async def admin_get_conversion_funnel(
    db: DatabaseManager = Depends(get_db)
):
    """
    [ADMIN] Get conversion funnel statistics.
    """
    with db.get_connection() as conn:
        from psycopg2.extras import RealDictCursor
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status != 'draft' THEN 1 ELSE 0 END) as confirmed,
                SUM(CASE WHEN status IN ('payment_verified', 'documents_review', 'approved') THEN 1 ELSE 0 END) as paid,
                SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
                SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected,
                SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled
            FROM registrations
        """)
        
        row = cursor.fetchone()
        
        total = row["total"] or 0
        confirmed = row["confirmed"] or 0
        paid = row["paid"] or 0
        approved = row["approved"] or 0
    
    return {
        "success": True,
        "data": {
            "funnel": {
                "started": total,
                "confirmed": confirmed,
                "paid": paid,
                "approved": approved,
                "rejected": row["rejected"] or 0,
                "cancelled": row["cancelled"] or 0
            },
            "conversion_rates": {
                "started_to_confirmed": round((confirmed / total * 100), 1) if total > 0 else 0,
                "confirmed_to_paid": round((paid / confirmed * 100), 1) if confirmed > 0 else 0,
                "paid_to_approved": round((approved / paid * 100), 1) if paid > 0 else 0,
            }
        }
    }

from fastapi.responses import FileResponse
import os

@router.get("/documents/display/{document_id}")
def display_document(document_id: int, db: DatabaseManager = Depends(get_db)):
    """
    Display a document file inline in browser based on document_id.
    """
    # Ambil dokumen dari DB
    with db.get_connection() as conn:
        from psycopg2.extras import RealDictCursor
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT id, file_name, file_path, file_type
            FROM registration_documents
            WHERE id = %s
        """, (document_id,))
        
        doc = cursor.fetchone()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    
    file_path = doc["file_path"]
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File tidak ada di server")
    
    # Tampilkan inline
    return FileResponse(
        path=file_path,
        media_type=doc.get("file_type", "application/octet-stream"),
        filename=doc["file_name"],
        headers={"Content-Disposition": "inline"}
    )


# =============================================================================
# ADMIN - EXPORT
# =============================================================================

@router.get("/admin/export/registrations")
async def admin_export_registrations(
    status: Optional[RegistrationStatus] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    format: str = Query("json", pattern="^(json|csv)$"),
    db: DatabaseManager = Depends(get_db)
):
    """
    [ADMIN] Export registrations data.
    """
    with db.get_connection() as conn:
        from psycopg2.extras import RealDictCursor
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        where_clauses = ["status != 'draft'"]
        params = []
        
        if status:
            where_clauses.append("status = %s")
            params.append(status.value)
        
        if date_from:
            where_clauses.append("DATE(created_at) >= %s")
            params.append(date_from)
        
        if date_to:
            where_clauses.append("DATE(created_at) <= %s")
            params.append(date_to)
        
        where_sql = " AND ".join(where_clauses)
        
        cursor.execute(f"""
            SELECT 
                registration_number,
                user_id,
                status,
                student_data->>'nama_lengkap' as nama_lengkap,
                student_data->>'nama_sekolah' as nama_sekolah,
                student_data->>'tingkatan' as tingkatan,
                student_data->>'program' as program,
                student_data->>'jenis_kelamin' as jenis_kelamin,
                student_data->>'tempat_lahir' as tempat_lahir,
                student_data->>'tanggal_lahir' as tanggal_lahir,
                created_at,
                confirmed_at,
                updated_at
            FROM registrations
            WHERE {where_sql}
            ORDER BY created_at DESC
        """, params if params else None)
        
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]
    
    if format == "csv":
        import csv
        import io
        
        output = io.StringIO()
        if data:
            writer = csv.DictWriter(output, fieldnames=data[0].keys())
            writer.writeheader()
            for row in data:
                # Convert datetime to string
                for k, v in row.items():
                    if isinstance(v, datetime):
                        row[k] = v.isoformat()
                writer.writerow(row)
        
        return JSONResponse(
            content={"success": True, "csv_data": output.getvalue()},
            headers={"Content-Disposition": "attachment; filename=registrations.csv"}
        )
    
    # Convert datetime for JSON
    for row in data:
        for k, v in row.items():
            if isinstance(v, datetime):
                row[k] = v.isoformat()
    
    return {
        "success": True,
        "data": {
            "registrations": data,
            "total": len(data),
            "exported_at": datetime.now().isoformat()
        }
    }