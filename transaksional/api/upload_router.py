from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from transaksional.app.config import settings
from transaksional.app.database import get_db_manager
from transaksional.app.session_state import get_session_manager
from transaksional.app.file_storage import get_file_storage, FileValidationError

router = APIRouter(
    prefix=settings.transactional_prefix,
    tags=["Upload"]
)


class UploadResponse(BaseModel):
    success: bool
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    message: str


@router.post("/upload/document", response_model=UploadResponse)
async def upload_document(
    session_id: str = Form(...),
    field_name: str = Form(...),
    file: UploadFile = File(...)
):
    """Upload a document for registration."""
    try:
        file_storage = get_file_storage()
        result = await file_storage.save_file(
            file=file,
            session_id=session_id,
            file_type=field_name
        )
        
        db = get_db_manager()
        db.save_document(
            session_id=session_id,
            field_name=field_name,
            file_name=result["file_name"],
            file_path=result["file_path"],
            file_size=result["file_size"],
            file_type=result["content_type"]
        )
        
        session_manager = get_session_manager()
        session = session_manager.get_session(session_id)
        if session:
            session.set_field(field_name, result["file_path"])
            session.set_document(field_name, result)
        
        return UploadResponse(
            success=True,
            file_path=result["file_path"],
            file_name=result["file_name"],
            file_size=result["file_size"],
            message=f"✅ {field_name} berhasil diupload!"
        )
    except FileValidationError as e:
        return UploadResponse(success=False, message=f"❌ {e.message}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{session_id}")
async def get_documents(session_id: str):
    """Get all documents for a session."""
    db = get_db_manager()
    return {
        "session_id": session_id,
        "documents": db.get_documents(session_id=session_id)
    }