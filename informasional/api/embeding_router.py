from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import os, sys, yaml, torch
from dotenv import load_dotenv
from typing import List, Dict, Any

from informasional.utils.db import SessionLocal
from informasional.models.chunk import ChunkModel
from informasional.models.embedding import EmbeddingModel

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from collections import defaultdict
from datetime import datetime
from transaksional.app.config import settings
router = APIRouter(prefix=f"{settings.informational_prefix}/embed", tags=["Embedding"])



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
# Project root & Config
# ==============================
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)
load_dotenv()

config_path = os.path.join(ROOT_DIR, "config", "config.yaml")
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)


def resolve_env_vars(d):
    if isinstance(d, dict):
        return {k: resolve_env_vars(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [resolve_env_vars(v) for v in d]
    elif isinstance(d, str) and d.startswith("${") and d.endswith("}"):
        return os.getenv(d[2:-1], "")
    return d


config = resolve_env_vars(config)


# ==============================
# Embeddings Setup
# ==============================
embedding_cfg = config["embeddings"]
EMBEDDING_MODEL_NAME = None

if embedding_cfg["model"] == "openai":
    EMBEDDING_MODEL_NAME = embedding_cfg["openai"]["model_name"]
    embeddings = OpenAIEmbeddings(
        model=EMBEDDING_MODEL_NAME,
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )

elif embedding_cfg["model"] == "huggingface":
    EMBEDDING_MODEL_NAME = embedding_cfg["huggingface"]["model_name"]
    device = embedding_cfg["huggingface"].get("device", "cpu")
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        model_kwargs={"device": device},
        encode_kwargs={"normalize_embeddings": True}
    )

else:
    raise RuntimeError("Embedding model tidak didukung")


# ==============================
# ChromaDB Setup
# ==============================
chroma_cfg = config["vectordb"]["chroma"]
collection_metadata = {"hnsw:space": chroma_cfg.get("distance_function", "cosine")}

vectorstore = Chroma(
    collection_name=chroma_cfg["collection_name"],
    persist_directory=chroma_cfg["persist_directory"],
    embedding_function=embeddings,
    collection_metadata=collection_metadata
)


# ==============================
# HELPER: Sanitize metadata
# ==============================
def sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize metadata untuk ChromaDB
    ChromaDB hanya support: str, int, float, bool
    """
    if metadata is None:
        return {}
    
    safe = {}
    for k, v in metadata.items():
        if v is None:
            safe[k] = ""
        elif isinstance(v, bool):
            safe[k] = v
        elif isinstance(v, (int, float)):
            safe[k] = v
        elif isinstance(v, str):
            safe[k] = v
        elif isinstance(v, list):
            safe[k] = ", ".join(str(item) for item in v)
        else:
            safe[k] = str(v)
    return safe


# ==============================
# API: Embed Pending Chunks
# ==============================
@router.post("/")
def embed_chunks(limit: int = 100, db: Session = Depends(get_db)):
    """
    Embed pending chunks:
    
    1. Ambil chunks dengan status 'pending'
    2. Generate embeddings batch
    3. Simpan vector ke PostgreSQL (audit/backup)
    4. Simpan ke ChromaDB (search)
    5. Update status jadi 'embedded'
    """
    
    # Get pending chunks
    chunks = (
        db.query(ChunkModel)
        .filter(ChunkModel.status == "pending")
        .order_by(ChunkModel.document_id, ChunkModel.chunk_index)  # Order by document
        .limit(limit)
        .all()
    )

    if not chunks:
        return {
            "message": "No pending chunks to embed",
            "total_embedded": 0
        }

    # 1️⃣ Generate embeddings batch
    contents = [chunk.content for chunk in chunks]
    vectors = embeddings.embed_documents(contents)
    vector_dimension = len(vectors[0]) if vectors else 0

    # 2️⃣ Prepare documents untuk ChromaDB
    documents: List[Document] = []
    chroma_ids: List[str] = []
    
    # Track statistics
    docs_processed = defaultdict(int)

    for chunk, vector in zip(chunks, vectors):
        # Prepare metadata
        metadata = chunk.metadata_json or {}
        
        # Pastikan document_id ada
        if not chunk.document_id and metadata.get("document_id"):
            chunk.document_id = metadata.get("document_id")
        
        # Sanitize metadata untuk ChromaDB
        safe_metadata = sanitize_metadata(metadata)
        
        # KUNCI: Pastikan document_id ada di metadata ChromaDB
        safe_metadata["document_id"] = chunk.document_id or f"chunk_{chunk.id}"
        safe_metadata["chunk_index"] = chunk.chunk_index
        safe_metadata["total_chunks"] = chunk.total_chunks
        safe_metadata["db_chunk_id"] = chunk.id  # Reference ke PostgreSQL
        
        # Simpan vector ke PostgreSQL
        embedding_record = EmbeddingModel(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            vector=vector,
            embedding_model=EMBEDDING_MODEL_NAME,
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

    # 3️⃣ Commit ke PostgreSQL
    db.commit()

    # 4️⃣ Add ke ChromaDB
    vectorstore.add_documents(documents, ids=chroma_ids)

    return {
        "message": "Chunks embedded successfully",
        "total_embedded": len(chunks),
        "documents_processed": len(docs_processed),
        "chunks_per_document": dict(docs_processed),
        "embedding_model": EMBEDDING_MODEL_NAME,
        "vector_dimension": vector_dimension,
        "storage": {
            "postgresql": "vectors saved for audit",
            "chromadb": "vectors indexed for search"
        }
    }


# ==============================
# API: Embed Specific Document
# ==============================
@router.post("/document/{document_id}")
def embed_document_chunks(
    document_id: str,  # document_id tracking, bukan DB ID
    db: Session = Depends(get_db)
):
    """
    Embed semua chunks untuk document_id tertentu
    """
    chunks = (
        db.query(ChunkModel)
        .filter(ChunkModel.document_id == document_id)
        .filter(ChunkModel.status == "pending")
        .order_by(ChunkModel.chunk_index)
        .all()
    )
    
    if not chunks:
        return {
            "message": f"No pending chunks for document_id: {document_id}",
            "total_embedded": 0
        }
    
    # Process sama seperti embed_chunks
    contents = [chunk.content for chunk in chunks]
    vectors = embeddings.embed_documents(contents)
    vector_dimension = len(vectors[0]) if vectors else 0
    
    documents: List[Document] = []
    chroma_ids: List[str] = []
    
    for chunk, vector in zip(chunks, vectors):
        metadata = chunk.metadata_json or {}
        safe_metadata = sanitize_metadata(metadata)
        safe_metadata["document_id"] = document_id
        safe_metadata["chunk_index"] = chunk.chunk_index
        safe_metadata["total_chunks"] = chunk.total_chunks
        safe_metadata["db_chunk_id"] = chunk.id
        
        db.add(EmbeddingModel(
            chunk_id=chunk.id,
            document_id=document_id,
            vector=vector,
            embedding_model=EMBEDDING_MODEL_NAME,
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
    vectorstore.add_documents(documents, ids=chroma_ids)
    
    return {
        "message": f"Document chunks embedded",
        "document_id": document_id,
        "total_embedded": len(chunks)
    }


# ==============================
# API: Get Vectorstore Info
# ==============================
@router.get("/info")
def get_vectorstore_info():
    """Get ChromaDB collection info"""
    collection = vectorstore._collection
    count = collection.count()
    
    # Get unique document_ids
    doc_ids = set()
    if count > 0:
        try:
            all_meta = collection.get(include=['metadatas'])
            for meta in all_meta.get('metadatas', []):
                if meta and 'document_id' in meta:
                    doc_ids.add(meta['document_id'])
        except:
            pass
    
    return {
        "collection_name": collection.name,
        "total_chunks": count,
        "unique_documents": len(doc_ids),
        "document_ids": list(doc_ids)[:20],  # Sample
        "distance_function": collection.metadata.get("hnsw:space", "unknown"),
        "embedding_model": EMBEDDING_MODEL_NAME
    }


# ==============================
# API: Get Chunks for Document (dari ChromaDB)
# ==============================
@router.get("/document/{document_id}/chunks")
def get_document_chunks_from_vectorstore(document_id: str):
    """
    Get semua chunks untuk document_id dari ChromaDB
    Useful untuk debug aggregation
    """
    collection = vectorstore._collection
    
    try:
        results = collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"]
        )
        
        if not results['ids']:
            return {
                "document_id": document_id,
                "total_chunks": 0,
                "message": "No chunks found"
            }
        
        chunks = []
        for i, (chunk_id, content, metadata) in enumerate(zip(
            results['ids'],
            results['documents'],
            results['metadatas']
        )):
            chunks.append({
                "chroma_id": chunk_id,
                "chunk_index": metadata.get('chunk_index', i),
                "content_preview": content[:200] + "..." if len(content) > 200 else content,
                "metadata": metadata
            })
        
        # Sort by chunk_index
        chunks.sort(key=lambda x: x['chunk_index'])
        
        return {
            "document_id": document_id,
            "total_chunks": len(chunks),
            "chunks": chunks
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==============================
# API: Delete Embedding
# ==============================
@router.delete("/{chunk_id}")
def delete_embedding(chunk_id: int, db: Session = Depends(get_db)):
    """
    Hapus embedding dari PostgreSQL dan ChromaDB
    Reset chunk status ke 'pending'
    """
    # Get chunk untuk info
    chunk = db.query(ChunkModel).filter(ChunkModel.id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    
    # Hapus dari PostgreSQL embeddings
    embedding = db.query(EmbeddingModel).filter(
        EmbeddingModel.chunk_id == chunk_id
    ).first()
    
    if embedding:
        db.delete(embedding)
    
    # Update chunk status
    chunk.status = "pending"
    chunk.embedded_at = None
    
    db.commit()
    
    # Hapus dari ChromaDB
    try:
        # Coba berbagai ID format
        chroma_ids_to_try = [
            str(chunk_id),
            f"chunk_{chunk_id}",
            chunk.metadata_json.get("chunk_id") if chunk.metadata_json else None
        ]
        
        for cid in chroma_ids_to_try:
            if cid:
                try:
                    vectorstore.delete(ids=[cid])
                except:
                    pass
    except Exception as e:
        print(f"Warning: Could not delete from ChromaDB: {e}")
    
    return {
        "message": "Embedding deleted, chunk status reset to pending",
        "chunk_id": chunk_id
    }


# ==============================
# API: Delete All Embeddings for Document
# ==============================
@router.delete("/document/{document_id}")
def delete_document_embeddings(
    document_id: str,
    db: Session = Depends(get_db)
):
    """
    Hapus semua embeddings untuk document_id
    Reset semua chunks ke 'pending'
    """
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
    
    # Delete embeddings dari PostgreSQL
    db.query(EmbeddingModel).filter(
        EmbeddingModel.chunk_id.in_(chunk_ids)
    ).delete(synchronize_session=False)
    
    # Reset chunk status
    for chunk in chunks:
        chunk.status = "pending"
        chunk.embedded_at = None
    
    db.commit()
    
    # Delete dari ChromaDB
    try:
        collection = vectorstore._collection
        results = collection.get(
            where={"document_id": document_id},
            include=[]
        )
        
        if results['ids']:
            vectorstore.delete(ids=results['ids'])
    except Exception as e:
        print(f"Warning: Could not delete from ChromaDB: {e}")
    
    return {
        "message": f"All embeddings deleted for document",
        "document_id": document_id,
        "chunks_reset": len(chunks)
    }


# ==============================
# API: Re-embed Chunks
# ==============================
@router.post("/reembed")
def reembed_chunks(chunk_ids: List[int], db: Session = Depends(get_db)):
    """
    Re-embed specific chunks
    Useful setelah ganti embedding model
    """
    # Get chunks
    chunks = db.query(ChunkModel).filter(
        ChunkModel.id.in_(chunk_ids)
    ).all()
    
    if not chunks:
        return {"message": "No chunks found", "reembedded": 0}
    
    # Delete existing embeddings
    db.query(EmbeddingModel).filter(
        EmbeddingModel.chunk_id.in_(chunk_ids)
    ).delete(synchronize_session=False)
    
    # Delete from ChromaDB
    for chunk in chunks:
        try:
            chroma_id = chunk.metadata_json.get("chunk_id") if chunk.metadata_json else f"chunk_{chunk.id}"
            vectorstore.delete(ids=[chroma_id])
        except:
            pass
    
    # Reset status
    for chunk in chunks:
        chunk.status = "pending"
        chunk.embedded_at = None
    
    db.commit()
    
    # Re-embed
    return embed_chunks(limit=len(chunks), db=db)


# ==============================
# API: Statistics
# ==============================
@router.get("/stats")
def get_embedding_stats(db: Session = Depends(get_db)):
    """Get embedding statistics"""
    
    # PostgreSQL stats
    total_chunks = db.query(ChunkModel).count()
    pending_chunks = db.query(ChunkModel).filter(ChunkModel.status == "pending").count()
    embedded_chunks = db.query(ChunkModel).filter(ChunkModel.status == "embedded").count()
    total_embeddings = db.query(EmbeddingModel).count()
    
    # Unique documents
    unique_docs = db.query(func.count(func.distinct(ChunkModel.document_id))).scalar()
    
    # ChromaDB stats
    collection = vectorstore._collection
    chroma_count = collection.count()
    
    return {
        "postgresql": {
            "total_chunks": total_chunks,
            "pending_chunks": pending_chunks,
            "embedded_chunks": embedded_chunks,
            "total_embeddings": total_embeddings,
            "unique_documents": unique_docs
        },
        "chromadb": {
            "total_vectors": chroma_count,
            "collection_name": collection.name
        },
        "sync_status": "ok" if embedded_chunks == chroma_count else "mismatch",
        "embedding_model": EMBEDDING_MODEL_NAME
    }
