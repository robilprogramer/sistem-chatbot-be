from sqlalchemy import Column, Integer, ForeignKey, JSON, DateTime, String
from sqlalchemy.sql import func
from informasional.utils.db import Base

class EmbeddingModel(Base):
    __tablename__ = "document_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    
    # ===== REFERENCES =====
    chunk_id = Column(Integer, ForeignKey("document_chunks.id"), nullable=False, index=True)
    
    # document_id untuk tracking (sama dengan di ChunkModel)
    document_id = Column(String(100), index=True, nullable=True)
    
    # ===== EMBEDDING DATA =====
    vector = Column(JSON, nullable=False)  # Simpan embedding sebagai JSON/array
    
    # ===== METADATA =====
    embedding_model = Column(String(100), nullable=True)  # e.g., "text-embedding-3-small"
    vector_dimension = Column(Integer, nullable=True)  # e.g., 1536
    
    # ===== TIMESTAMPS =====
    created_at = Column(DateTime(timezone=True), server_default=func.now())

