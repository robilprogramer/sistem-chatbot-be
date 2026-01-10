from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import os, sys, yaml, torch
from dotenv import load_dotenv
from typing import List

from informasional.utils.db import SessionLocal
from informasional.models.chunk import ChunkModel
from informasional.models.embedding import EmbeddingModel

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings

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
# Project root
# ==============================
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

load_dotenv()

# ==============================
# Load config.yaml
# ==============================
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
# Embeddings
# ==============================
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

else:
    raise RuntimeError("Embedding model tidak didukung")

# ==============================
# ChromaDB
# ==============================
chroma_cfg = config["vectordb"]["chroma"]
collection_metadata = {"hnsw:space": chroma_cfg.get("distance_function", "cosine")}

vectorstore = Chroma(
    collection_name=chroma_cfg["collection_name"],
    persist_directory=chroma_cfg["persist_directory"],
    embedding_function=embeddings,
    collection_metadata=collection_metadata
)

def sanitize_metadata(metadata: dict) -> dict:
    """Sanitize metadata untuk ChromaDB (hanya str, int, float, bool)"""
    safe = {}
    for k, v in metadata.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            safe[k] = v
        elif isinstance(v, list):
            safe[k] = ", ".join(map(str, v))
        else:
            safe[k] = str(v)
    return safe

# ==============================
# API: Embed pending chunks
# ==============================
@router.post("/")
def embed_chunks(limit: int = 100, db: Session = Depends(get_db)):
    """
    Embed pending chunks:
    1. Generate embeddings batch (efisien)
    2. Simpan vector ke PostgreSQL (audit/backup)
    3. Simpan ke ChromaDB untuk similarity search
    """
    
    chunks = (
        db.query(ChunkModel)
        .filter(ChunkModel.status == "pending")
        .limit(limit)
        .all()
    )

    if not chunks:
        return {"message": "No pending chunks"}

    # 1️⃣ Generate embeddings secara batch (lebih efisien)
    contents = [chunk.content for chunk in chunks]
    vectors = embeddings.embed_documents(contents)

    # 2️⃣ Siapkan documents untuk ChromaDB
    documents: List[Document] = []
    chunk_ids: List[str] = []

    for chunk, vector in zip(chunks, vectors):
        # Simpan vector ke PostgreSQL (untuk audit/backup)
        db.add(
            EmbeddingModel(
                chunk_id=chunk.id,
                vector=vector
            )
        )

        # Siapkan document untuk ChromaDB
        safe_metadata = sanitize_metadata(chunk.metadata_json or {})
        safe_metadata["chunk_id"] = chunk.id  # Track chunk_id di metadata
        
        documents.append(
            Document(
                page_content=chunk.content,
                metadata=safe_metadata
            )
        )
        
        chunk_ids.append(str(chunk.id))

        # Update status
        chunk.status = "embedded"

    # 3️⃣ Commit ke PostgreSQL
    db.commit()

    # 4️⃣ Add ke ChromaDB dengan explicit IDs
    # ChromaDB akan re-embed, tapi kita track dengan chunk_id
    vectorstore.add_documents(documents, ids=chunk_ids)

    return {
        "message": "Chunks embedded & added to Knowledge Base",
        "total_chunks": len(chunks),
        "storage": {
            "postgresql": "vectors saved for audit",
            "chromadb": "vectors indexed for search"
        }
    }

# ==============================
# API: Get vectorstore info
# ==============================
@router.get("/info")
def get_vectorstore_info():
    """Debug info untuk ChromaDB collection"""
    collection = vectorstore._collection
    return {
        "name": collection.name,
        "count": collection.count(),
        "metadata": collection.metadata,
        "distance_function": collection.metadata.get("hnsw:space", "unknown")
    }

# ==============================
# API: Delete embedding by chunk_id
# ==============================
@router.delete("/{chunk_id}")
def delete_embedding(chunk_id: int, db: Session = Depends(get_db)):
    """
    Hapus embedding dari PostgreSQL dan ChromaDB
    """
    # Hapus dari PostgreSQL
    embedding = db.query(EmbeddingModel).filter(
        EmbeddingModel.chunk_id == chunk_id
    ).first()
    
    if not embedding:
        raise HTTPException(status_code=404, detail="Embedding not found")
    
    db.delete(embedding)
    
    # Update chunk status
    chunk = db.query(ChunkModel).filter(ChunkModel.id == chunk_id).first()
    if chunk:
        chunk.status = "pending"
    
    db.commit()
    
    # Hapus dari ChromaDB
    try:
        vectorstore.delete(ids=[str(chunk_id)])
    except Exception as e:
        # ChromaDB mungkin tidak punya ID ini
        pass
    
    return {
        "message": "Embedding deleted",
        "chunk_id": chunk_id
    }

# ==============================
# API: Re-embed specific chunks
# ==============================
@router.post("/reembed")
def reembed_chunks(chunk_ids: List[int], db: Session = Depends(get_db)):
    """
    Re-embed chunks yang sudah pernah di-embed
    Berguna kalau ganti embedding model
    """
    chunks = db.query(ChunkModel).filter(
        ChunkModel.id.in_(chunk_ids)
    ).all()
    
    if not chunks:
        return {"message": "No chunks found"}
    
    # Hapus embeddings lama
    db.query(EmbeddingModel).filter(
        EmbeddingModel.chunk_id.in_(chunk_ids)
    ).delete(synchronize_session=False)
    
    # Hapus dari ChromaDB
    vectorstore.delete(ids=[str(cid) for cid in chunk_ids])
    
    # Set status ke pending
    for chunk in chunks:
        chunk.status = "pending"
    
    db.commit()
    
    # Re-embed
    return embed_chunks(limit=len(chunks), db=db)