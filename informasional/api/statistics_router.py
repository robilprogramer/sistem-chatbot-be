# routes/statistics.py
"""
Statistics API Router for Dashboard
Provides comprehensive statistics for knowledge base management
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from typing import Dict, Any
import os
import sys
import yaml
from dotenv import load_dotenv
from sqlalchemy import text
from informasional.utils.db import SessionLocal
from informasional.models.document import Document, DocumentStatus
from informasional.models.chunk import ChunkModel
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
import torch
from transaksional.app.config import settings
router = APIRouter(prefix=f"{settings.informational_prefix}/statistics", tags=["Statistics"])



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
# Setup ChromaDB & Config
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

# Setup embeddings
embedding_cfg = config["embeddings"]
if embedding_cfg["model"] == "openai":
    embeddings = OpenAIEmbeddings(
        model=embedding_cfg["openai"]["model_name"],
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )
elif embedding_cfg["model"] == "huggingface":
    device = embedding_cfg["huggingface"].get("device", "cpu")
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"
    embeddings = HuggingFaceEmbeddings(
        model_name=embedding_cfg["huggingface"]["model_name"],
        model_kwargs={"device": device},
        encode_kwargs={"normalize_embeddings": True}
    )

# Setup ChromaDB
chroma_cfg = config["vectordb"]["chroma"]
vectorstore = Chroma(
    collection_name=chroma_cfg["collection_name"],
    embedding_function=embeddings,
    persist_directory=chroma_cfg["persist_directory"]
)


# ==============================
# Helper Functions
# ==============================
def get_document_stats(db: Session) -> Dict[str, Any]:
    """Get document statistics"""
    
    # Total documents
    total_docs = db.query(func.count(Document.id)).scalar()
    
    # By status
    status_stats = db.query(
        Document.status,
        func.count(Document.id)
    ).group_by(Document.status).all()
    
    by_status = {status.value: count for status, count in status_stats}
    
    # By jenjang (from metadata)
    jenjang_stats = db.query(
        func.json_extract_path_text(Document.extra_metadata, 'jenjang'),
        func.count(Document.id)
    ).group_by(
        func.json_extract_path_text(Document.extra_metadata, 'jenjang')
    ).filter(
        func.json_extract_path_text(Document.extra_metadata, 'jenjang').isnot(None)
    ).all()
    
    by_jenjang = {jenjang or 'Unknown': count for jenjang, count in jenjang_stats}
    
    # By kategori (from metadata)
    kategori_stats = db.query(
        func.json_extract_path_text(Document.extra_metadata, 'kategori'),
        func.count(Document.id)
    ).group_by(
        func.json_extract_path_text(Document.extra_metadata, 'kategori')
    ).filter(
        func.json_extract_path_text(Document.extra_metadata, 'kategori').isnot(None)
    ).all()
    
    by_kategori = {kategori or 'Unknown': count for kategori, count in kategori_stats}
    
    return {
        "total": total_docs,
        "by_status": by_status,
        "by_jenjang": by_jenjang,
        "by_kategori": by_kategori
    }


def get_chunk_stats(db: Session) -> Dict[str, Any]:
    """Get chunk statistics"""
    
    # Total chunks
    total_chunks = db.query(func.count(ChunkModel.id)).scalar()
    
    # Embedded chunks (status = 'embedded')
    embedded_chunks = db.query(func.count(ChunkModel.id)).filter(
        ChunkModel.status == "embedded"
    ).scalar()
    
    # Pending chunks
    pending_chunks = db.query(func.count(ChunkModel.id)).filter(
        ChunkModel.status == "pending"
    ).scalar()
    
    return {
        "total": total_chunks,
        "embedded": embedded_chunks,
        "pending": pending_chunks
    }


def get_vectorstore_stats() -> Dict[str, Any]:
    """Get ChromaDB vectorstore statistics"""
    
    try:
        collection = vectorstore._collection
        total_vectors = collection.count()
        
        # Get sample metadata to analyze
        sample = collection.get(limit=1000, include=["metadatas"])
        
        by_jenjang = {}
        by_kategori = {}
        
        if sample and sample.get("metadatas"):
            for meta in sample["metadatas"]:
                # Count by jenjang
                jenjang = meta.get("jenjang", "Unknown")
                by_jenjang[jenjang] = by_jenjang.get(jenjang, 0) + 1
                
                # Count by kategori
                kategori = meta.get("kategori", "Unknown")
                by_kategori[kategori] = by_kategori.get(kategori, 0) + 1
        
        return {
            "total": total_vectors,
            "by_jenjang": by_jenjang,
            "by_kategori": by_kategori
        }
    
    except Exception as e:
        print(f"Error getting vectorstore stats: {e}")
        return {
            "total": 0,
            "by_jenjang": {},
            "by_kategori": {}
        }


def get_knowledge_entries_stats(db: Session) -> Dict[str, Any]:
    """
    Get knowledge entries statistics
    Knowledge entries = embedded chunks in vectorstore
    """
    
    vectorstore_stats = get_vectorstore_stats()
    chunk_stats = get_chunk_stats(db)
    
    return {
        "total": vectorstore_stats["total"],
        "active": chunk_stats["embedded"],
        "by_jenjang": vectorstore_stats["by_jenjang"],
        "by_kategori": vectorstore_stats["by_kategori"]
    }


def get_staging_stats(db: Session) -> Dict[str, Any]:
    """
    Get staging statistics
    Staging = documents that are processed but not yet embedded
    """
    
    # Pending review = completed documents with pending chunks
    pending_review = db.query(func.count(Document.id)).filter(
        Document.status == DocumentStatus.COMPLETED
    ).scalar()
    
    # Check how many have embedded chunks
    embedded_count = db.query(func.count(ChunkModel.id)).filter(
        ChunkModel.status == "embedded"
    ).scalar()
    
    # Approved = documents with all chunks embedded
    approved = embedded_count
    
    return {
        "pending_review": pending_review,
        "approved": approved
    }


# ==============================
# API Endpoints
# ==============================

@router.get("/")
def get_statistics(db: Session = Depends(get_db)):
    """
    Get comprehensive statistics for dashboard
    
    Returns:
        - documents: Document statistics
        - knowledge_entries: Knowledge base entries statistics
        - chunks: Chunk processing statistics
        - staging: Staging area statistics
        - vectorstore: Vector database statistics
    """
    
    try:
        # Gather all statistics
        stats = {
            "documents": get_document_stats(db),
            "knowledge_entries": get_knowledge_entries_stats(db),
            "chunks": get_chunk_stats(db),
            "staging": get_staging_stats(db),
            "vectorstore": get_vectorstore_stats()
        }
        
        return {
            "success": True,
            "message": "Statistics retrieved successfully",
            "statistics": stats
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve statistics: {str(e)}"
        )


@router.get("/documents")
def get_document_statistics(db: Session = Depends(get_db)):
    """Get only document statistics"""
    
    try:
        return {
            "success": True,
            "statistics": get_document_stats(db)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chunks")
def get_chunk_statistics(db: Session = Depends(get_db)):
    """Get only chunk statistics"""
    
    try:
        return {
            "success": True,
            "statistics": get_chunk_stats(db)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vectorstore")
def get_vectorstore_statistics():
    """Get only vectorstore statistics"""
    
    try:
        return {
            "success": True,
            "statistics": get_vectorstore_stats()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge-entries")
def get_knowledge_statistics(db: Session = Depends(get_db)):
    """Get only knowledge entries statistics"""
    
    try:
        return {
            "success": True,
            "statistics": get_knowledge_entries_stats(db)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """
    Health check for statistics service
    """
    try:
        # Test database connection
        db.execute(text("SELECT 1"))

        # Test vectorstore connection
        vectorstore._collection.count()

        return {
            "status": "healthy",
            "database": "connected",
            "vectorstore": "connected"
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
