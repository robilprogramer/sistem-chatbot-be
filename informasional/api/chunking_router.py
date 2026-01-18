"""
Chunking Router - Process documents dari DB ke chunks

FLOW:
1. Document dengan status COMPLETED
2. Chunk content menggunakan EnhancedChunker
3. Simpan chunks ke ChunkModel dengan status 'pending'
4. Chunks siap untuk di-embed

ENDPOINTS:
- POST /chunks/process-pending     : Auto process pending documents
- POST /chunks/process/{id}        : Process specific document
- GET  /chunks/stats               : Get chunking statistics
- GET  /chunks/                    : List all chunks
- GET  /chunks/{id}                : Get chunk by ID
- GET  /chunks/by-document/{doc_id}: Get chunks by document_id
- DELETE /chunks/{id}              : Delete chunk
- DELETE /chunks/by-source/{id}    : Delete chunks by source document
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime

from informasional.utils.enhanced_chunker import EnhancedChunker, DocumentProcessor
from informasional.utils.metadata_extractor import MetadataExtractor
from informasional.models.document import Document, DocumentStatus
from informasional.models.chunk import ChunkModel
from informasional.utils.db import SessionLocal
from informasional.repositories.master_repository import MasterRepository
from informasional.repositories.document_repository import DocumentRepository
from informasional.schemas.chunking_schema import (
    ChunkingResponse, 
    ChunkResponse, 
    StandardResponse,ChunkUpdateRequest
)
from transaksional.app.config import settings


# ============================================================================
# ROUTER SETUP
# ============================================================================
router = APIRouter(
    prefix=f"{settings.informational_prefix}/chunks", 
    tags=["Chunking"]
)

# Config path - sesuaikan dengan struktur project
CONFIG_PATH = "informasional/config/config.yaml"


# ============================================================================
# DEPENDENCIES
# ============================================================================
def get_db():
    """Database session dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_chunker() -> EnhancedChunker:
    """Get chunker instance dengan config dari YAML"""
    return EnhancedChunker(config_path=CONFIG_PATH)


def get_processor(db: Session) -> DocumentProcessor:
    """Get document processor dengan chunker dan metadata extractor"""
    chunker = get_chunker()
    master_repo = MasterRepository(db)
    extractor = MetadataExtractor(master_repo)
    return DocumentProcessor(chunker=chunker, metadata_extractor=extractor)


# ============================================================================
# HELPER: Save chunks ke database
# ============================================================================
def save_chunks_to_db(
    db: Session,
    chunks: List,  # List of langchain Document
    source_document_id: int = None
) -> List[ChunkModel]:
    """
    Simpan chunks ke database dengan document_id tracking
    
    Args:
        db: Database session
        chunks: List of langchain Document objects
        source_document_id: FK ke table documents
    
    Returns:
        List of saved ChunkModel instances
    """
    if not chunks:
        return []
    
    saved_chunks = []
    
    for chunk in chunks:
        if chunk is None:
            continue
        
        metadata = chunk.metadata or {}
        
        chunk_model = ChunkModel(
            # Document tracking
            document_id=metadata.get("document_id", ""),
            source_document_id=source_document_id or metadata.get("source_document_id"),
            
            # Chunk positioning
            chunk_index=metadata.get("chunk_index", 0),
            total_chunks=metadata.get("total_chunks", 1),
            
            # Content
            filename=metadata.get("filename", metadata.get("source", "")),
            content=chunk.page_content,
            
            # Metadata
            metadata_json=metadata,
            
            # Status
            status="pending"
        )
        
        db.add(chunk_model)
        saved_chunks.append(chunk_model)
    
    db.commit()
    
    # Refresh untuk dapat ID
    for chunk in saved_chunks:
        db.refresh(chunk)
    
    return saved_chunks


# ============================================================================
# API: Process Pending Documents (Auto)
# ============================================================================
@router.post("/process-pending", response_model=StandardResponse)
def process_pending_documents(
    limit: int = Query(default=10, ge=1, le=100, description="Max documents to process"),
    db: Session = Depends(get_db)
):
    """
    Process dokumen yang sudah COMPLETED tapi belum di-chunk
    
    Flow:
    1. Ambil documents dengan status COMPLETED
    2. Filter yang belum punya chunks
    3. Chunk dan simpan ke database
    
    Returns:
        StandardResponse dengan detail processing
    """
    # Get completed documents
    doc_repo = DocumentRepository(db)
    documents, total = doc_repo.get_all(
        status=DocumentStatus.COMPLETED,
        limit=limit
    )
    
    if not documents:
        return StandardResponse(
            status_code=200,
            message="No completed documents to process",
            data={"processed": 0, "total_chunks": 0}
        )
    
    # Initialize processor
    processor = get_processor(db)
    
    processed_count = 0
    total_chunks_created = 0
    results = []
    errors = []
    
    for doc in documents:
        try:
            # Skip jika sudah ada chunks untuk document ini
            existing_count = db.query(func.count(ChunkModel.id)).filter(
                ChunkModel.source_document_id == doc.id
            ).scalar()
            
            if existing_count > 0:
                continue
            
            # Skip jika tidak ada content
            if not doc.raw_text or not doc.raw_text.strip():
                continue
            
            # Build metadata dari document
            metadata = {
                "source": doc.original_filename or doc.filename,
                "filename": doc.original_filename or doc.filename,
                "file_type": doc.mime_type,
                "total_pages": doc.total_pages or 0,
                "extraction_method": doc.extraction_method or "",
            }
            
            # Process document
            chunks = processor.process_document(
                filename=doc.original_filename or doc.filename,
                content=doc.raw_text,
                metadata=metadata,
                source_document_id=doc.id
            )
            
            # Save chunks
            saved = save_chunks_to_db(db, chunks, source_document_id=doc.id)
            
            processed_count += 1
            total_chunks_created += len(saved)
            
            results.append({
                "document_id": doc.id,
                "filename": doc.original_filename,
                "chunks_created": len(saved),
                "document_tracking_id": chunks[0].metadata.get("document_id") if chunks else None
            })
            
        except Exception as e:
            errors.append({
                "document_id": doc.id,
                "filename": doc.original_filename,
                "error": str(e)
            })
    
    return StandardResponse(
        status_code=200,
        message=f"Processed {processed_count} documents, created {total_chunks_created} chunks",
        data={
            "processed_documents": processed_count,
            "total_chunks": total_chunks_created,
            "details": results,
            "errors": errors if errors else None
        }
    )


# ============================================================================
# API: Process Specific Document
# ============================================================================
@router.post("/process/{document_id}", response_model=StandardResponse)
def process_document_by_id(
    document_id: int,
    force: bool = Query(default=False, description="Force re-chunk even if chunks exist"),
    db: Session = Depends(get_db)
):
    """
    Process specific document by ID
    
    Args:
        document_id: ID dari table documents
        force: Jika True, hapus chunks lama dan buat ulang
    
    Returns:
        StandardResponse dengan detail chunks yang dibuat
    """
    # Get document
    doc_repo = DocumentRepository(db)
    doc = doc_repo.get_by_id(document_id)
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if doc.status != DocumentStatus.COMPLETED:
        raise HTTPException(
            status_code=400, 
            detail=f"Document not ready. Current status: {doc.status.value}"
        )
    
    if not doc.raw_text:
        raise HTTPException(status_code=400, detail="Document has no extracted text")
    
    # Check existing chunks
    existing_chunks = db.query(ChunkModel).filter(
        ChunkModel.source_document_id == document_id
    ).all()
    
    if existing_chunks and not force:
        return StandardResponse(
            status_code=200,
            message=f"Document already has {len(existing_chunks)} chunks. Use force=true to re-chunk.",
            data={
                "document_id": document_id,
                "existing_chunks": len(existing_chunks),
                "action": "skipped"
            }
        )
    
    # Delete existing chunks if force
    if existing_chunks and force:
        for chunk in existing_chunks:
            db.delete(chunk)
        db.commit()
        print(f"🗑️  Deleted {len(existing_chunks)} existing chunks")
    
    # Initialize processor
    processor = get_processor(db)
    
    # Build metadata
    metadata = {
        "source": doc.original_filename or doc.filename,
        "filename": doc.original_filename or doc.filename,
        "file_type": doc.mime_type,
        "total_pages": doc.total_pages or 0,
        "extraction_method": doc.extraction_method or "",
    }
    
    # Process
    chunks = processor.process_document(
        filename=doc.original_filename or doc.filename,
        content=doc.raw_text,
        metadata=metadata,
        source_document_id=doc.id
    )
    
    # Save
    saved = save_chunks_to_db(db, chunks, source_document_id=doc.id)
    
    return StandardResponse(
        status_code=200,
        message=f"Created {len(saved)} chunks for document",
        data={
            "document_id": document_id,
            "filename": doc.original_filename,
            "chunks_created": len(saved),
            "document_tracking_id": chunks[0].metadata.get("document_id") if chunks else None,
            "chunk_ids": [c.id for c in saved],
            "action": "re-chunked" if force and existing_chunks else "chunked"
        }
    )


# ============================================================================
# API: Get Statistics
# ============================================================================
@router.get("/stats", response_model=StandardResponse)
def get_chunk_statistics(db: Session = Depends(get_db)):
    """
    Get comprehensive chunk statistics
    
    Returns:
        - Count by status (pending, embedded)
        - Average chunk length
        - Chunks per document distribution
    """
    # Count by status
    status_counts = db.query(
        ChunkModel.status,
        func.count(ChunkModel.id)
    ).group_by(ChunkModel.status).all()
    
    status_dict = {status: count for status, count in status_counts}
    
    # Total and average
    total_count = sum(status_dict.values())
    
    avg_length = db.query(
        func.avg(func.length(ChunkModel.content))
    ).scalar() or 0
    
    # Unique documents
    unique_docs = db.query(
        func.count(func.distinct(ChunkModel.document_id))
    ).scalar() or 0
    
    # Get chunker config
    chunker = get_chunker()
    
    return StandardResponse(
        status_code=200,
        message="Chunk statistics retrieved",
        data={
            "total_chunks": total_count,
            "by_status": {
                "pending": status_dict.get("pending", 0),
                "embedded": status_dict.get("embedded", 0),
                "other": sum(v for k, v in status_dict.items() if k not in ["pending", "embedded"])
            },
            "unique_documents": unique_docs,
            "avg_chunk_length": round(float(avg_length), 2),
            "chunker_config": chunker.config
        }
    )


# ============================================================================
# API: List Chunks
# ============================================================================
@router.get("/", response_model=StandardResponse)
def get_chunks(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status: Optional[str] = Query(default=None, description="Filter by status: pending, embedded"),
    document_id: Optional[str] = Query(default=None, description="Filter by document_id"),
    db: Session = Depends(get_db)
):
    """
    Get all chunks with optional filters
    
    Args:
        skip: Pagination offset
        limit: Max results (1-200)
        status: Filter by status
        document_id: Filter by document tracking ID
    """
    query = db.query(ChunkModel)
    
    if status:
        query = query.filter(ChunkModel.status == status)
    
    if document_id:
        query = query.filter(ChunkModel.document_id == document_id)
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    chunks = query.order_by(
        ChunkModel.document_id, 
        ChunkModel.chunk_index
    ).offset(skip).limit(limit).all()
    
    return StandardResponse(
        status_code=200,
        message=f"Retrieved {len(chunks)} chunks",
        data={
            "total": total,
            "skip": skip,
            "limit": limit,
            "chunks": [
                ChunkResponse(
                    id=c.id,
                    # content=c.content[:200] + "..." if len(c.content) > 200 else c.content,
                    content=c.content,
                    metadata=c.metadata_json
                )
                for c in chunks
            ]
        }
    )


# ============================================================================
# API: Get Chunk by ID
# ============================================================================
@router.get("/{chunk_id}", response_model=StandardResponse)
def get_chunk(chunk_id: int, db: Session = Depends(get_db)):
    """Get single chunk by ID with full content"""
    chunk = db.query(ChunkModel).filter(ChunkModel.id == chunk_id).first()
    
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    
    return StandardResponse(
        status_code=200,
        message="Chunk retrieved",
        data=ChunkResponse(
            id=chunk.id,
            content=chunk.content,
            metadata=chunk.metadata_json
        )
    )


# ============================================================================
# API: Get Chunks by Document Tracking ID
# ============================================================================
@router.get("/by-document/{document_id}", response_model=StandardResponse)
def get_chunks_by_document_id(document_id: str, db: Session = Depends(get_db)):
    """
    Get all chunks untuk document_id tertentu (document tracking ID)
    
    Chunks akan diurutkan berdasarkan chunk_index
    """
    chunks = db.query(ChunkModel).filter(
        ChunkModel.document_id == document_id
    ).order_by(ChunkModel.chunk_index).all()
    
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail=f"No chunks found for document_id: {document_id}"
        )
    
    return StandardResponse(
        status_code=200,
        message=f"{len(chunks)} chunks retrieved",
        data={
            "document_id": document_id,
            "total_chunks": chunks[0].total_chunks if chunks else 0,
            "chunks": [
                ChunkResponse(
                    id=c.id,
                    content=c.content,
                    metadata=c.metadata_json
                )
                for c in chunks
            ]
        }
    )


# ============================================================================
# API: Get Chunks by Source Document ID
# ============================================================================
@router.get("/by-source/{source_document_id}", response_model=StandardResponse)
def get_chunks_by_source_document(
    source_document_id: int, 
    db: Session = Depends(get_db)
):
    """
    Get all chunks untuk source_document_id (FK ke table documents)
    """
    chunks = db.query(ChunkModel).filter(
        ChunkModel.source_document_id == source_document_id
    ).order_by(ChunkModel.chunk_index).all()
    
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail=f"No chunks found for source_document_id: {source_document_id}"
        )
    
    return StandardResponse(
        status_code=200,
        message=f"{len(chunks)} chunks retrieved",
        data={
            "source_document_id": source_document_id,
            "document_id": chunks[0].document_id if chunks else None,
            "total_chunks": len(chunks),
            "chunks": [
                ChunkResponse(
                    id=c.id,
                    content=c.content,
                    metadata=c.metadata_json
                )
                for c in chunks
            ]
        }
    )

# ==============================
# CRUD: Update chunk
# ==============================
@router.put("/{chunk_id}", response_model=StandardResponse)
def update_chunk(chunk_id: int, payload: ChunkUpdateRequest, db: Session = Depends(get_db)):
    chunk = db.query(ChunkModel).filter(ChunkModel.id == chunk_id).first()
    
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    
    if payload.content:
        chunk.content = payload.content
    if payload.metadata:
        chunk.metadata_json = payload.metadata
    
    db.commit()
    db.refresh(chunk)
    
    return StandardResponse(
        status_code=200,
        message="Chunk updated successfully",
        data=ChunkResponse(
            id=chunk.id,
            content=chunk.content,
            metadata=chunk.metadata_json
        )
    )


# ============================================================================
# API: Delete Chunk
# ============================================================================
@router.delete("/{chunk_id}", response_model=StandardResponse)
def delete_chunk(chunk_id: int, db: Session = Depends(get_db)):
    """Delete single chunk by ID"""
    chunk = db.query(ChunkModel).filter(ChunkModel.id == chunk_id).first()
    
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    
    document_id = chunk.document_id
    db.delete(chunk)
    db.commit()
    
    return StandardResponse(
        status_code=200,
        message="Chunk deleted successfully",
        data={
            "deleted_chunk_id": chunk_id,
            "document_id": document_id
        }
    )


# ============================================================================
# API: Delete Chunks by Source Document
# ============================================================================
@router.delete("/by-source/{source_document_id}", response_model=StandardResponse)
def delete_chunks_by_source_document(
    source_document_id: int, 
    db: Session = Depends(get_db)
):
    """
    Delete all chunks untuk source_document_id
    
    Berguna untuk re-chunking document
    """
    chunks = db.query(ChunkModel).filter(
        ChunkModel.source_document_id == source_document_id
    ).all()
    
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail=f"No chunks found for source_document_id: {source_document_id}"
        )
    
    count = len(chunks)
    document_id = chunks[0].document_id if chunks else None
    
    for chunk in chunks:
        db.delete(chunk)
    db.commit()
    
    return StandardResponse(
        status_code=200,
        message=f"Deleted {count} chunks",
        data={
            "source_document_id": source_document_id,
            "document_id": document_id,
            "deleted_count": count
        }
    )


# ============================================================================
# API: Preview Chunking (Dry Run)
# ============================================================================
@router.post("/preview/{document_id}", response_model=StandardResponse)
def preview_chunking(
    document_id: int,
    db: Session = Depends(get_db)
):
    """
    Preview hasil chunking tanpa menyimpan ke database
    
    Berguna untuk testing dan tuning chunk_size/overlap
    """
    # Get document
    doc_repo = DocumentRepository(db)
    doc = doc_repo.get_by_id(document_id)
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if not doc.raw_text:
        raise HTTPException(status_code=400, detail="Document has no extracted text")
    
    # Initialize processor
    processor = get_processor(db)
    
    # Build metadata
    metadata = {
        "source": doc.original_filename or doc.filename,
        "filename": doc.original_filename or doc.filename,
    }
    
    # Process (without saving)
    chunks = processor.process_document(
        filename=doc.original_filename or doc.filename,
        content=doc.raw_text,
        metadata=metadata,
        source_document_id=doc.id
    )
    
    # Get statistics
    stats = processor.chunker.get_statistics(chunks)
    
    return StandardResponse(
        status_code=200,
        message=f"Preview: {len(chunks)} chunks would be created",
        data={
            "document_id": document_id,
            "filename": doc.original_filename,
            "content_length": len(doc.raw_text),
            "chunks_preview": [
                {
                    "index": i,
                    "length": len(c.page_content),
                    "preview": c.page_content[:100] + "..." if len(c.page_content) > 100 else c.page_content,
                    "metadata": {
                        "chunk_id": c.metadata.get("chunk_id"),
                        "is_first": c.metadata.get("is_first_chunk"),
                        "is_last": c.metadata.get("is_last_chunk")
                    }
                }
                for i, c in enumerate(chunks[:5])  # Show first 5 only
            ],
            "statistics": stats,
            "note": "This is a preview. Use POST /process/{id} to save chunks."
        }
    )