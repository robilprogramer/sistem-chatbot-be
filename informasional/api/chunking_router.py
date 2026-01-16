"""
Chunking Router - Process documents dari DB ke chunks

FLOW:
1. Baca Document dengan status COMPLETED
2. Chunk content
3. Simpan chunks ke ChunkModel dengan status 'pending'
4. Chunks siap untuk di-embed
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List,Optional
from informasional.utils.enhanced_chunker import EnhancedChunker, DocumentProcessor
from informasional.utils.metadata_extractor import MetadataExtractor
from informasional.models.document import Document, DocumentStatus
from informasional.utils.db import SessionLocal
from informasional.repositories.master_repository import MasterRepository
from informasional.repositories.document_repository import DocumentRepository
from informasional.schemas.chunking_schema import ChunkingRequest, ChunkingResponse, ChunkResponse, StandardResponse,ChunkUpdateRequest,ChunkBulkUpdateRequest
from transaksional.app.config import settings
from informasional.models.chunk import ChunkModel


router = APIRouter(prefix=f"{settings.informational_prefix}/chunks", tags=["Chunking"])


# ==============================
# DB Dependency
# ==============================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==============================
# HELPER: Save chunks ke database
# ==============================
def save_chunks_to_db(
    db: Session,
    chunks: List,  # List of langchain Document
    source_document_id: int = None
) -> List[ChunkModel]:
    """
    Simpan chunks ke database dengan document_id tracking
    """
    saved_chunks = []
    
    for chunk in chunks:
        if chunk is None:
            continue
        
        metadata = chunk.metadata or {}
        
        # Create ChunkModel
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


# ==============================
# API: Process Documents (Auto dari DB)
# ==============================
@router.post("/process-pending", response_model=StandardResponse)
def process_pending_documents(
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    Process dokumen yang sudah COMPLETED tapi belum di-chunk
    
    Flow:
    1. Ambil documents dengan status COMPLETED
    2. Filter yang belum punya chunks
    3. Chunk dan simpan
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
            data={"processed": 0}
        )
    
    # Initialize chunker
    chunker = EnhancedChunker(config_path="informasional/config/config.yaml")
    master_repo = MasterRepository(db)
    extractor = MetadataExtractor(master_repo)
    processor = DocumentProcessor(chunker=chunker, metadata_extractor=extractor)
    
    processed_count = 0
    total_chunks = 0
    results = []
    
    for doc in documents:
        # Skip jika sudah ada chunks untuk document ini
        existing_chunks = db.query(ChunkModel).filter(
            ChunkModel.source_document_id == doc.id
        ).count()
        
        if existing_chunks > 0:
            continue
        
        # Skip jika tidak ada content
        if not doc.raw_text or not doc.raw_text.strip():
            continue
        
        # Build metadata dari document
        metadata = {
            "source": doc.original_filename or doc.filename,
            "filename": doc.original_filename or doc.filename,
            "file_type": doc.mime_type,
            "total_pages": doc.total_pages,
            "extraction_method": doc.extraction_method,
        }
        
        # Chunk document
        chunks = processor.process_document(
            filename=doc.original_filename or doc.filename,
            content=doc.raw_text,
            metadata=metadata,
            source_document_id=doc.id
        )
        
        # Save chunks
        saved = save_chunks_to_db(db, chunks, source_document_id=doc.id)
        
        processed_count += 1
        total_chunks += len(saved)
        
        results.append({
            "document_id": doc.id,
            "filename": doc.original_filename,
            "chunks_created": len(saved),
            "document_tracking_id": chunks[0].metadata.get("document_id") if chunks else None
        })
    
    return StandardResponse(
        status_code=200,
        message=f"Processed {processed_count} documents, created {total_chunks} chunks",
        data={
            "processed_documents": processed_count,
            "total_chunks": total_chunks,
            "details": results
        }
    )


# ==============================
# API: Process Specific Document
# ==============================
@router.post("/process/{document_id}", response_model=StandardResponse)
def process_document_by_id(
    document_id: int,
    force: bool = False,  # Force re-chunk even if chunks exist
    db: Session = Depends(get_db)
):
    """
    Process specific document by ID
    
    Args:
        document_id: ID dari table documents
        force: Jika True, hapus chunks lama dan buat ulang
    """
    doc_repo = DocumentRepository(db)
    doc = doc_repo.get_by_id(document_id)
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if doc.status != DocumentStatus.COMPLETED:
        raise HTTPException(
            status_code=400, 
            detail=f"Document not ready. Status: {doc.status}"
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
                "existing_chunks": len(existing_chunks)
            }
        )
    
    # Delete existing chunks if force
    if existing_chunks and force:
        for chunk in existing_chunks:
            db.delete(chunk)
        db.commit()
    
    # Initialize chunker
    chunker = EnhancedChunker(config_path="informasional/config/config.yaml")
    master_repo = MasterRepository(db)
    extractor = MetadataExtractor(master_repo)
    processor = DocumentProcessor(chunker=chunker, metadata_extractor=extractor)
    
    # Build metadata
    metadata = {
        "source": doc.original_filename or doc.filename,
        "filename": doc.original_filename or doc.filename,
        "file_type": doc.file_type,
        "total_pages": doc.total_pages,
        "extraction_method": doc.extraction_method,
    }
    
    # Chunk
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
            "chunk_ids": [c.id for c in saved]
        }
    )


# ==============================
# API: Manual Chunk (Original)
# ==============================
@router.post("/process", response_model=ChunkingResponse)
def chunk_documents(payload: ChunkingRequest, db: Session = Depends(get_db)):
    """
    Manual chunking endpoint (backward compatible)
    """
    chunker = EnhancedChunker(config_path="informasional/config/config.yaml")
    master_repo = MasterRepository(db)
    docrepo = DocumentRepository(db)
    extractor = MetadataExtractor(master_repo)
    processor = DocumentProcessor(chunker=chunker, metadata_extractor=extractor)

    documents = []
    
    for doc in payload.documents:
        doc_data = doc.dict()
        source_doc_id = None

        # CASE: content kosong → ambil dari DB
        if not doc_data.get("content") or not doc_data["content"].strip():
            db_doc = docrepo.get_by_filename(doc_data["filename"])

            if not db_doc or not db_doc.raw_text:
                raise HTTPException(
                    status_code=400,
                    detail=f"Document '{doc_data['filename']}' has no extracted text"
                )

            doc_data["filename"] = db_doc.original_filename
            doc_data["content"] = db_doc.raw_text
            source_doc_id = db_doc.id
        
        doc_data["source_document_id"] = source_doc_id
        documents.append(doc_data)
    
    chunks = processor.process_multiple_documents(documents)
    saved_chunks = save_chunks_to_db(db, chunks)

    return ChunkingResponse(
        total_chunks=len(saved_chunks),
        chunks=[
            ChunkResponse(
                id=c.id,
                content=c.content, 
                metadata=c.metadata_json
            ) 
            for c in saved_chunks if c is not None
        ]
    )


# ==============================
# API: Get Pending Chunks Count
# ==============================
@router.get("/pending/count", response_model=StandardResponse)
def get_pending_count(db: Session = Depends(get_db)):
    """
    Get count of pending chunks (ready for embedding)
    """
    pending_count = db.query(ChunkModel).filter(
        ChunkModel.status == "pending"
    ).count()
    
    embedded_count = db.query(ChunkModel).filter(
        ChunkModel.status == "embedded"
    ).count()
    
    total_count = db.query(ChunkModel).count()
    
    return StandardResponse(
        status_code=200,
        message="Chunk statistics",
        data={
            "pending": pending_count,
            "embedded": embedded_count,
            "total": total_count
        }
    )


# ==============================
# API: Get Chunks by Document ID
# ==============================
@router.get("/by-document/{document_id}", response_model=StandardResponse)
def get_chunks_by_document_id(document_id: str, db: Session = Depends(get_db)):
    """
    Get all chunks untuk document_id tertentu
    (document_id adalah tracking ID, bukan DB ID)
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
        data=[
            ChunkResponse(
                id=c.id,
                content=c.content,
                metadata=c.metadata_json
            )
            for c in chunks
        ]
    )


# ==============================
# CRUD: Get all chunks
# ==============================
@router.get("/", response_model=StandardResponse)
def get_chunks(
    skip: int = 0, 
    limit: int = 100, 
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all chunks with optional status filter"""
    query = db.query(ChunkModel)
    
    if status:
        query = query.filter(ChunkModel.status == status)
    
    chunks = query.offset(skip).limit(limit).all()
    
    return StandardResponse(
        status_code=200,
        message=f"{len(chunks)} chunks retrieved",
        data=[
            ChunkResponse(
                id=c.id,
                content=c.content, 
                metadata=c.metadata_json
            ) 
            for c in chunks
        ]
    )


# ==============================
# CRUD: Get chunk by ID
# ==============================
@router.get("/{chunk_id}", response_model=StandardResponse)
def get_chunk(chunk_id: int, db: Session = Depends(get_db)):
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


# ==============================
# CRUD: Delete chunk
# ==============================
@router.delete("/{chunk_id}", response_model=StandardResponse)
def delete_chunk(chunk_id: int, db: Session = Depends(get_db)):
    chunk = db.query(ChunkModel).filter(ChunkModel.id == chunk_id).first()
    
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    
    db.delete(chunk)
    db.commit()
    
    return StandardResponse(
        status_code=200,
        message="Chunk deleted successfully",
        data=None
    )


# ==============================
# CRUD: Get chunks by filename
# ==============================
@router.get("/by-filename/{filename}", response_model=StandardResponse)
def get_chunks_by_filename(filename: str, db: Session = Depends(get_db)):
    chunks = db.query(ChunkModel).filter(
        ChunkModel.filename == filename
    ).order_by(ChunkModel.chunk_index).all()

    if not chunks:
        raise HTTPException(
            status_code=404,
            detail=f"No chunks found for filename: {filename}"
        )

    return StandardResponse(
        status_code=200,
        message=f"{len(chunks)} chunks retrieved for filename {filename}",
        data=[
            ChunkResponse(
                id=c.id,
                content=c.content,
                metadata=c.metadata_json
            )
            for c in chunks
        ]
    )


# ==============================
# CRUD: Bulk update by filename
# ==============================
@router.put("/bulk-update/by-filename/{filename}", response_model=StandardResponse)
def bulk_update_chunks_by_filename(
    filename: str,
    payload: ChunkBulkUpdateRequest,
    db: Session = Depends(get_db)
):
    repo = MasterRepository(db)

    updated_count = repo.bulk_update_chunks_by_filename(
        filename=filename,
        updates=[item.dict(exclude_unset=True) for item in payload.chunks]
    )

    if updated_count == 0:
        raise HTTPException(
            status_code=404,
            detail="No chunks updated (check filename or IDs)"
        )

    return StandardResponse(
        status_code=200,
        message=f"{updated_count} chunks updated for filename {filename}",
        data={
            "filename": filename,
            "updated_count": updated_count
        }
    )
