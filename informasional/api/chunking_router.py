from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from informasional.utils.enhanced_chunker import EnhancedChunker, DocumentProcessor
from informasional.utils.metadata_extractor import MetadataExtractor
from informasional.utils.db import SessionLocal
from informasional.repositories.master_repository import MasterRepository
from informasional.repositories.document_repository import DocumentRepository
from informasional.schemas.chunking_schema import ChunkingRequest, ChunkingResponse, ChunkResponse, StandardResponse,ChunkUpdateRequest,ChunkBulkUpdateRequest
from transaksional.app.config import settings


router = APIRouter(prefix=f"{settings.informational_prefix}/chunks", tags=["Chunking"])

# Dependency DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------------------
# CREATE / Chunk Documents
# ------------------------------
@router.post("/process", response_model=ChunkingResponse)
def chunk_documents(payload: ChunkingRequest, db: Session = Depends(get_db)):
    chunker = EnhancedChunker(config_path="config/config.yaml")
    master_repo = MasterRepository(db)
    docrepo = DocumentRepository(db)
    extractor = MetadataExtractor(master_repo)
    processor = DocumentProcessor(chunker=chunker, metadata_extractor=extractor)

    # documents = [doc.dict() for doc in payload.documents]
    documents = []

    for doc in payload.documents:
        doc_data = doc.dict()

        # 🔍 CASE: content kosong → ambil dari DB
        if not doc_data.get("content") or not doc_data["content"].strip():
            db_doc = docrepo.get_by_filename(doc_data["filename"])

            if not db_doc or not db_doc.raw_text:
                raise HTTPException(
                    status_code=400,
                    detail=f"Document '{doc_data['filename']}' has no extracted text"
                )

            # inject raw_text dari DB
            doc_data["filename"]= db_doc.original_filename
            doc_data["content"] = db_doc.raw_text

        documents.append(doc_data)
    chunks = processor.process_multiple_documents(documents)

    saved_chunks = []
    for chunk in chunks:
        if chunk is None:
            continue
        metadata = chunk.metadata or {}
        filename = metadata.get("filename")
        saved = master_repo.save_chunk(
            content=chunk.page_content,
            metadata=metadata,
            filename=filename
        )
        saved_chunks.append(saved)

    return ChunkingResponse(
        total_chunks=len(saved_chunks),
        chunks=[ChunkResponse(content=c.content, metadata=c.metadata_json) for c in saved_chunks if c is not None]
    )

# ------------------------------
# READ / Get all chunks
# ------------------------------
@router.get("/", response_model=StandardResponse)
def get_chunks(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    repo = MasterRepository(db)
    chunks = repo.get_all_chunks(skip=skip, limit=limit)
    chunk_list = [ChunkResponse(id=c.id,content=c.content, metadata=c.metadata_json) for c in chunks]
    
    return StandardResponse(
        status_code=200,
        message=f"{len(chunk_list)} chunks retrieved",
        data=chunk_list
    )

# ------------------------------
# READ / Get chunk by ID
# ------------------------------
@router.get("/{chunk_id}", response_model=StandardResponse)
def get_chunk(chunk_id: int, db: Session = Depends(get_db)):
    repo = MasterRepository(db)
    chunk = repo.get_chunk(chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    chunk_response = ChunkResponse(
        id=chunk.id,
        content=chunk.content,
        metadata=chunk.metadata_json
    )
    
    
    return StandardResponse(
        status_code=200,
        message=f"1 chunks retrieved",
        data=chunk_response
    )

# ------------------------------
# UPDATE chunk
# ------------------------------
@router.put("/{chunk_id}", response_model=StandardResponse)
def update_chunk(chunk_id: int, payload: ChunkUpdateRequest, db: Session = Depends(get_db)):
    repo = MasterRepository(db)
    
    updated = repo.update_chunk(
        chunk_id=chunk_id,
        content=payload.content,
        metadata=payload.metadata
    )

    if not updated:
        raise HTTPException(status_code=404, detail="Chunk not found")
    
    chunk_response = ChunkResponse(
        content=updated.content,
        metadata=updated.metadata_json
    )

    return StandardResponse(
        status_code=200,
        message="Chunk updated successfully",
        data=chunk_response
    )

# ------------------------------
# DELETE chunk
# ------------------------------
@router.delete("/{chunk_id}", response_model=StandardResponse)
def delete_chunk(chunk_id: int, db: Session = Depends(get_db)):
    repo = MasterRepository(db)
    success = repo.delete_chunk(chunk_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Chunk not found")
    
    return StandardResponse(
        status_code=200,
        message="Chunk deleted successfully",
        data=None
    )
# ------------------------------
# READ / Get chunks by filename
# ------------------------------
@router.get("/by-filename/{filename}", response_model=StandardResponse)
def get_chunks_by_filename(filename: str, db: Session = Depends(get_db)):
    repo = MasterRepository(db)
    chunks = repo.get_chunks_by_filename(filename)

    if not chunks:
        raise HTTPException(
            status_code=404,
            detail=f"No chunks found for filename: {filename}"
        )

    chunk_list = [
        ChunkResponse(
            id=c.id,
            content=c.content,
            metadata=c.metadata_json
        )
        for c in chunks
    ]

    return StandardResponse(
        status_code=200,
        message=f"{len(chunk_list)} chunks retrieved for filename {filename}",
        data=chunk_list
    )
    
  # ------------------------------
# UPDATE / Bulk update by filename
# ------------------------------
@router.put(
    "/bulk-update/by-filename/{filename}",
    response_model=StandardResponse
)
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
