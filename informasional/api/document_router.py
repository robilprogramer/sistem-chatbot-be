
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from typing import Optional
import math
from informasional.utils.db import SessionLocal
from informasional.services.document_service import DocumentService
from informasional.schemas.document_schema import (
    DocumentUploadResponse,
    DocumentProcessResponse,
    DocumentResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentRawTextUpdateRequest
)
from transaksional.app.config import settings

router = APIRouter(prefix=f"{settings.informational_prefix}/documents", tags=["Documents"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_document_service(db: Session = Depends(get_db)) -> DocumentService:
    """Dependency untuk DocumentService"""
    return DocumentService(db)

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    service: DocumentService = Depends(get_document_service)
):
    """
    Upload PDF document
    
    - **file**: PDF file to upload
    - Returns: document_id dan status
    """
    try:
        result = await service.upload_document(file)
        
        return DocumentUploadResponse(
            success=True,
            message="Document uploaded successfully",
            document_id=result["document_id"],
            filename=result["original_filename"],
            status=result["status"]
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.post("/{document_id}/process", response_model=DocumentProcessResponse)
def process_document(
    document_id: int,
    service: DocumentService = Depends(get_document_service)
):
    """
    Process uploaded document (extract content)
    
    - **document_id**: ID of the document to process
    - Returns: extraction results
    """
    try:
        result = service.process_document(document_id)
        
        return DocumentProcessResponse(
            success=result["success"],
            message="Document processed successfully",
            document_id=result["document_id"],
            raw_text_preview=result.get("raw_text_preview"),
            total_pages=result.get("total_pages"),
            text_length=result.get("text_length"),
            tables_count=result.get("tables_count"),
            images_count=result.get("images_count")
        )
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(
    document_id: int,
    service: DocumentService = Depends(get_document_service)
):
    """
    Get document by ID with full details including raw_text
    """
    document = service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return document

@router.get("/", response_model=DocumentListResponse)
def get_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status: Optional[str] = None,
    service: DocumentService = Depends(get_document_service)
):
    """
    Get all documents with pagination
    
    - **page**: Page number (starts from 1)
    - **page_size**: Number of items per page
    - **status**: Filter by status (pending, processing, completed, failed)
    """
    skip = (page - 1) * page_size
    documents, total = service.get_documents(skip=skip, limit=page_size, status=status)
    
    total_pages = math.ceil(total / page_size)
    
    return DocumentListResponse(
        total=total,
        documents=documents,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )

@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    service: DocumentService = Depends(get_document_service)
):
    """
    Delete document by ID
    """
    success = service.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {"success": True, "message": "Document deleted successfully"}

@router.get("/{document_id}/raw-text")
def get_raw_text(
    document_id: int,
    service: DocumentService = Depends(get_document_service)
):
    """
    Get only raw text dari document (untuk preview atau download)
    """
    document = service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if not document.raw_text:
        raise HTTPException(status_code=404, detail="Raw text not available. Document may not be processed yet.")
    
    return {
        "document_id": document.id,
        "filename": document.original_filename,
        "raw_text": document.raw_text,
        "text_length": document.text_length
    }
    
# ------------------------------
# UPDATE / Update raw text
# ------------------------------
@router.put("/{document_id}/raw-text")
def update_raw_text(
    document_id: int,
    payload: DocumentRawTextUpdateRequest,
    service: DocumentService = Depends(get_document_service)
):
    """
    Update raw_text document (manual correction / normalization)
    """
    try:
        document = service.update_raw_text(
            document_id=document_id,
            raw_text=payload.raw_text
        )
        return {
        "document_id": document.id,
        "filename": document.original_filename,
        "raw_text": document.raw_text,
        "text_length": document.text_length
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))    