
"""
Embedding Router - Embed chunks ke VectorStore

FLOW:
1. Get pending chunks dari PostgreSQL
2. Generate embeddings menggunakan EmbeddingManager
3. Simpan vector ke PostgreSQL (backup/audit)
4. Simpan ke ChromaDB (search) via VectorStoreManager
5. Update chunk status: pending → embedded

ENDPOINTS:
- POST /embed/                     : Embed pending chunks (batch)
- POST /embed/document/{id}        : Embed specific document chunks
- GET  /embed/stats                : Get embedding statistics
- GET  /embed/info                 : Get vectorstore info
- GET  /embed/document/{id}/chunks : Get chunks from vectorstore
- DELETE /embed/{chunk_id}         : Delete embedding
- DELETE /embed/document/{id}      : Delete all embeddings for document
- POST /embed/reembed              : Re-embed specific chunks
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict

from langchain_core.documents import Document

from informasional.utils.db import SessionLocal
from informasional.models.chunk import ChunkModel
from informasional.models.embedding import EmbeddingModel
from informasional.utils.embedding_utils import (
    get_embedding_manager,
    sanitize_metadata_for_chroma
)
from informasional.utils.vectorstore_utils import get_vectorstore
from informasional.schemas.embedding_schema import (
    StandardResponse,
    EmbeddingStatsResponse,
    VectorStoreInfoResponse
)
from transaksional.app.config import settings


# ============================================================================
# ROUTER SETUP
# ============================================================================
router = APIRouter(
    prefix=f"{settings.informational_prefix}/embed",
    tags=["Embedding"]
)

# Config path
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


def get_managers():
    """
    Get EmbeddingManager dan VectorStoreManager
    
    Menggunakan singleton pattern untuk konsistensi dengan retrieval
    """
    embedding_manager = get_embedding_manager(CONFIG_PATH)
    vectorstore_manager = get_vectorstore(CONFIG_PATH)
    return embedding_manager, vectorstore_manager


# ============================================================================
# API: Embed Pending Chunks (Batch)
# ============================================================================
@router.post("/", response_model=StandardResponse)
def embed_pending_chunks(
    limit: int = Query(default=100, ge=1, le=500, description="Max chunks to embed"),
    db: Session = Depends(get_db)
):
    """
    Embed pending chunks ke VectorStore
    
    Flow:
    1. Ambil chunks dengan status 'pending'
    2. Generate embeddings batch
    3. Simpan vector ke PostgreSQL (audit/backup)
    4. Simpan ke ChromaDB (search)
    5. Update status jadi 'embedded'
    
    Args:
        limit: Maximum chunks to process (default: 100, max: 500)
    
    Returns:
        Statistics about embedded chunks
    """
    # Get managers (singleton)
    embedding_manager, vectorstore_manager = get_managers()
    
    # Get pending chunks
    chunks = (
        db.query(ChunkModel)
        .filter(ChunkModel.status == "pending")
        .order_by(ChunkModel.document_id, ChunkModel.chunk_index)
        .limit(limit)
        .all()
    )
    
    if not chunks:
        return StandardResponse(
            status_code=200,
            message="No pending chunks to embed",
            data={"total_embedded": 0}
        )
    
    # 1️⃣ Generate embeddings batch
    contents = [chunk.content for chunk in chunks]
    vectors = embedding_manager.embed_documents(contents)
    vector_dimension = embedding_manager.get_dimension()
    
    # 2️⃣ Prepare documents untuk ChromaDB
    documents: List[Document] = []
    chroma_ids: List[str] = []
    
    # Track statistics
    docs_processed = defaultdict(int)
    
    for chunk, vector in zip(chunks, vectors):
        # Prepare metadata
        metadata = chunk.metadata_json or {}
        
        # Ensure document_id
        if not chunk.document_id and metadata.get("document_id"):
            chunk.document_id = metadata.get("document_id")
        
        # Sanitize metadata untuk ChromaDB
        safe_metadata = sanitize_metadata_for_chroma(metadata)
        
        # KUNCI: Pastikan tracking fields ada di metadata
        safe_metadata["document_id"] = chunk.document_id or f"chunk_{chunk.id}"
        safe_metadata["chunk_index"] = chunk.chunk_index
        safe_metadata["total_chunks"] = chunk.total_chunks
        safe_metadata["db_chunk_id"] = chunk.id  # Reference ke PostgreSQL
        safe_metadata["source_document_id"] = chunk.source_document_id or 0
        
        # 3️⃣ Simpan vector ke PostgreSQL (audit)
        embedding_record = EmbeddingModel(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            vector=vector,
            embedding_model=embedding_manager.model_name,
            vector_dimension=vector_dimension
        )
        db.add(embedding_record)
        
        # Prepare ChromaDB document
        documents.append(
            Document(
                page_content=chunk.content,
                metadata=safe_metadata
            )
        )
        
        # Use chunk_id dari metadata atau generate
        chroma_id = safe_metadata.get("chunk_id") or f"chunk_{chunk.id}"
        chroma_ids.append(chroma_id)
        
        # Update chunk status
        chunk.status = "embedded"
        chunk.embedded_at = datetime.utcnow()
        
        # Track
        docs_processed[chunk.document_id] += 1
    
    # 4️⃣ Commit ke PostgreSQL
    db.commit()
    
    # 5️⃣ Add ke ChromaDB
    vectorstore_manager.add_documents(documents, ids=chroma_ids)
    
    return StandardResponse(
        status_code=200,
        message=f"Successfully embedded {len(chunks)} chunks",
        data={
            "total_embedded": len(chunks),
            "documents_processed": len(docs_processed),
            "chunks_per_document": dict(docs_processed),
            "embedding_model": embedding_manager.model_name,
            "vector_dimension": vector_dimension,
            "storage": {
                "postgresql": "vectors saved for audit",
                "chromadb": "vectors indexed for search"
            }
        }
    )


# ============================================================================
# API: Embed Specific Document
# ============================================================================
@router.post("/document/{document_id}", response_model=StandardResponse)
def embed_document_chunks(
    document_id: str,  # document_id tracking, bukan DB ID
    db: Session = Depends(get_db)
):
    """
    Embed semua pending chunks untuk document_id tertentu
    
    Args:
        document_id: Document tracking ID (e.g., "Biaya_SD_2024_a1b2c3d4")
    """
    # Get managers
    embedding_manager, vectorstore_manager = get_managers()
    
    # Get pending chunks for document
    chunks = (
        db.query(ChunkModel)
        .filter(ChunkModel.document_id == document_id)
        .filter(ChunkModel.status == "pending")
        .order_by(ChunkModel.chunk_index)
        .all()
    )
    
    if not chunks:
        # Check if document exists but already embedded
        existing = db.query(ChunkModel).filter(
            ChunkModel.document_id == document_id
        ).count()
        
        if existing > 0:
            return StandardResponse(
                status_code=200,
                message=f"All chunks for document already embedded",
                data={
                    "document_id": document_id,
                    "total_chunks": existing,
                    "pending": 0
                }
            )
        
        raise HTTPException(
            status_code=404,
            detail=f"No chunks found for document_id: {document_id}"
        )
    
    # Generate embeddings
    contents = [chunk.content for chunk in chunks]
    vectors = embedding_manager.embed_documents(contents)
    vector_dimension = embedding_manager.get_dimension()
    
    # Process chunks
    documents: List[Document] = []
    chroma_ids: List[str] = []
    
    for chunk, vector in zip(chunks, vectors):
        metadata = chunk.metadata_json or {}
        safe_metadata = sanitize_metadata_for_chroma(metadata)
        
        # Ensure tracking fields
        safe_metadata["document_id"] = document_id
        safe_metadata["chunk_index"] = chunk.chunk_index
        safe_metadata["total_chunks"] = chunk.total_chunks
        safe_metadata["db_chunk_id"] = chunk.id
        
        # Save to PostgreSQL
        db.add(EmbeddingModel(
            chunk_id=chunk.id,
            document_id=document_id,
            vector=vector,
            embedding_model=embedding_manager.model_name,
            vector_dimension=vector_dimension
        ))
        
        # Prepare for ChromaDB
        documents.append(Document(
            page_content=chunk.content,
            metadata=safe_metadata
        ))
        
        chroma_id = safe_metadata.get("chunk_id") or f"chunk_{chunk.id}"
        chroma_ids.append(chroma_id)
        
        # Update status
        chunk.status = "embedded"
        chunk.embedded_at = datetime.utcnow()
    
    # Commit
    db.commit()
    vectorstore_manager.add_documents(documents, ids=chroma_ids)
    
    return StandardResponse(
        status_code=200,
        message=f"Embedded {len(chunks)} chunks for document",
        data={
            "document_id": document_id,
            "total_embedded": len(chunks),
            "embedding_model": embedding_manager.model_name
        }
    )


# ============================================================================
# API: Get Statistics
# ============================================================================
@router.get("/stats", response_model=StandardResponse)
def get_embedding_stats(db: Session = Depends(get_db)):
    """
    Get comprehensive embedding statistics
    
    Returns:
        - PostgreSQL: chunks by status, total embeddings
        - ChromaDB: total vectors, collection info
        - Sync status: check if counts match
    """
    embedding_manager, vectorstore_manager = get_managers()
    
    # PostgreSQL stats
    total_chunks = db.query(ChunkModel).count()
    pending_chunks = db.query(ChunkModel).filter(
        ChunkModel.status == "pending"
    ).count()
    embedded_chunks = db.query(ChunkModel).filter(
        ChunkModel.status == "embedded"
    ).count()
    total_embeddings = db.query(EmbeddingModel).count()
    
    # Unique documents
    unique_docs = db.query(
        func.count(func.distinct(ChunkModel.document_id))
    ).scalar() or 0
    
    # ChromaDB stats
    chroma_info = vectorstore_manager.get_collection_info()
    
    # Sync check
    sync_status = "ok" if embedded_chunks == chroma_info["total_vectors"] else "mismatch"
    
    return StandardResponse(
        status_code=200,
        message="Embedding statistics retrieved",
        data={
            "postgresql": {
                "total_chunks": total_chunks,
                "pending_chunks": pending_chunks,
                "embedded_chunks": embedded_chunks,
                "total_embeddings": total_embeddings,
                "unique_documents": unique_docs
            },
            "chromadb": {
                "total_vectors": chroma_info["total_vectors"],
                "collection_name": chroma_info["collection_name"],
                "unique_documents": chroma_info["unique_documents"]
            },
            "sync_status": sync_status,
            "embedding_config": {
                "model": embedding_manager.model_name,
                "dimension": embedding_manager.get_dimension(),
                "provider": embedding_manager.provider.value
            }
        }
    )


# ============================================================================
# API: Get VectorStore Info
# ============================================================================
@router.get("/info", response_model=StandardResponse)
def get_vectorstore_info():
    """Get ChromaDB collection information"""
    _, vectorstore_manager = get_managers()
    info = vectorstore_manager.get_collection_info()
    
    return StandardResponse(
        status_code=200,
        message="VectorStore info retrieved",
        data=info
    )


# ============================================================================
# API: Get Document Chunks from VectorStore
# ============================================================================
@router.get("/document/{document_id}/chunks", response_model=StandardResponse)
def get_document_chunks_from_vectorstore(document_id: str):
    """
    Get semua chunks untuk document_id dari ChromaDB
    
    Useful untuk:
    - Debug aggregation
    - Verify embedding
    - Reconstruct document
    """
    _, vectorstore_manager = get_managers()
    
    chunks = vectorstore_manager.get_by_document_id(document_id)
    
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail=f"No chunks found in vectorstore for document_id: {document_id}"
        )
    
    return StandardResponse(
        status_code=200,
        message=f"Retrieved {len(chunks)} chunks from vectorstore",
        data={
            "document_id": document_id,
            "total_chunks": len(chunks),
            "chunks": [
                {
                    "chroma_id": c["chroma_id"],
                    "chunk_index": c["chunk_index"],
                    "content_preview": c["content"][:200] + "..." if len(c["content"]) > 200 else c["content"],
                    "metadata": c["metadata"]
                }
                for c in chunks
            ]
        }
    )


# ============================================================================
# API: Delete Embedding
# ============================================================================
@router.delete("/{chunk_id}", response_model=StandardResponse)
def delete_embedding(chunk_id: int, db: Session = Depends(get_db)):
    """
    Delete embedding dari PostgreSQL dan ChromaDB
    Reset chunk status ke 'pending'
    """
    _, vectorstore_manager = get_managers()
    
    # Get chunk
    chunk = db.query(ChunkModel).filter(ChunkModel.id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    
    # Delete from PostgreSQL embeddings
    db.query(EmbeddingModel).filter(
        EmbeddingModel.chunk_id == chunk_id
    ).delete()
    
    # Reset chunk status
    chunk.status = "pending"
    chunk.embedded_at = None
    
    db.commit()
    
    # Delete from ChromaDB
    try:
        chroma_ids_to_try = [
            f"chunk_{chunk_id}",
            chunk.metadata_json.get("chunk_id") if chunk.metadata_json else None
        ]
        
        for cid in chroma_ids_to_try:
            if cid:
                try:
                    vectorstore_manager.delete([cid])
                except:
                    pass
    except Exception as e:
        print(f"⚠️ Could not delete from ChromaDB: {e}")
    
    return StandardResponse(
        status_code=200,
        message="Embedding deleted, chunk status reset to pending",
        data={
            "chunk_id": chunk_id,
            "document_id": chunk.document_id
        }
    )


# ============================================================================
# API: Delete All Embeddings for Document
# ============================================================================
@router.delete("/document/{document_id}", response_model=StandardResponse)
def delete_document_embeddings(
    document_id: str,
    db: Session = Depends(get_db)
):
    """
    Delete semua embeddings untuk document_id
    Reset semua chunks ke 'pending'
    """
    _, vectorstore_manager = get_managers()
    
    # Get all chunks
    chunks = db.query(ChunkModel).filter(
        ChunkModel.document_id == document_id
    ).all()
    
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail=f"No chunks found for document_id: {document_id}"
        )
    
    chunk_ids = [c.id for c in chunks]
    
    # Delete embeddings from PostgreSQL
    db.query(EmbeddingModel).filter(
        EmbeddingModel.chunk_id.in_(chunk_ids)
    ).delete(synchronize_session=False)
    
    # Reset chunk status
    for chunk in chunks:
        chunk.status = "pending"
        chunk.embedded_at = None
    
    db.commit()
    
    # Delete from ChromaDB
    deleted_count = vectorstore_manager.delete_by_filter({"document_id": document_id})
    
    return StandardResponse(
        status_code=200,
        message=f"All embeddings deleted for document",
        data={
            "document_id": document_id,
            "chunks_reset": len(chunks),
            "chroma_deleted": deleted_count
        }
    )


# ============================================================================
# API: Re-embed Chunks
# ============================================================================
@router.post("/reembed", response_model=StandardResponse)
def reembed_chunks(
    chunk_ids: List[int],
    db: Session = Depends(get_db)
):
    """
    Re-embed specific chunks
    
    Useful untuk:
    - Setelah ganti embedding model
    - Fix corrupted embeddings
    - Update after content change
    """
    embedding_manager, vectorstore_manager = get_managers()
    
    # Get chunks
    chunks = db.query(ChunkModel).filter(
        ChunkModel.id.in_(chunk_ids)
    ).all()
    
    if not chunks:
        return StandardResponse(
            status_code=200,
            message="No chunks found",
            data={"reembedded": 0}
        )
    
    # Delete existing embeddings from PostgreSQL
    db.query(EmbeddingModel).filter(
        EmbeddingModel.chunk_id.in_(chunk_ids)
    ).delete(synchronize_session=False)
    
    # Delete from ChromaDB
    for chunk in chunks:
        try:
            chroma_id = chunk.metadata_json.get("chunk_id") if chunk.metadata_json else f"chunk_{chunk.id}"
            vectorstore_manager.delete([chroma_id])
        except:
            pass
    
    # Reset status to pending
    for chunk in chunks:
        chunk.status = "pending"
        chunk.embedded_at = None
    
    db.commit()
    
    # Now re-embed (call embed endpoint logic)
    # Generate embeddings
    contents = [chunk.content for chunk in chunks]
    vectors = embedding_manager.embed_documents(contents)
    vector_dimension = embedding_manager.get_dimension()
    
    documents: List[Document] = []
    chroma_ids: List[str] = []
    
    for chunk, vector in zip(chunks, vectors):
        metadata = chunk.metadata_json or {}
        safe_metadata = sanitize_metadata_for_chroma(metadata)
        safe_metadata["document_id"] = chunk.document_id
        safe_metadata["chunk_index"] = chunk.chunk_index
        safe_metadata["total_chunks"] = chunk.total_chunks
        safe_metadata["db_chunk_id"] = chunk.id
        
        db.add(EmbeddingModel(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            vector=vector,
            embedding_model=embedding_manager.model_name,
            vector_dimension=vector_dimension
        ))
        
        documents.append(Document(
            page_content=chunk.content,
            metadata=safe_metadata
        ))
        
        chroma_id = safe_metadata.get("chunk_id") or f"chunk_{chunk.id}"
        chroma_ids.append(chroma_id)
        
        chunk.status = "embedded"
        chunk.embedded_at = datetime.utcnow()
    
    db.commit()
    vectorstore_manager.add_documents(documents, ids=chroma_ids)
    
    return StandardResponse(
        status_code=200,
        message=f"Re-embedded {len(chunks)} chunks",
        data={
            "reembedded": len(chunks),
            "chunk_ids": chunk_ids,
            "embedding_model": embedding_manager.model_name
        }
    )