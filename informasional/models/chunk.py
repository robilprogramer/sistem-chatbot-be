from sqlalchemy import Column, Integer, Text, String, JSON, DateTime, ForeignKey
from sqlalchemy.sql import func
from informasional.utils.db import Base



class ChunkModel(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    
    # ===== DOCUMENT TRACKING (KUNCI untuk aggregation) =====
    # document_id: ID unik untuk dokumen asal (untuk menggabungkan chunks)
    document_id = Column(String(100), index=True, nullable=False)
    
    # Foreign key ke document asli (opsional, untuk relasi)
    source_document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    
    # ===== CHUNK POSITIONING =====
    chunk_index = Column(Integer, nullable=False, default=0)  # Urutan chunk dalam dokumen
    total_chunks = Column(Integer, nullable=False, default=1)  # Total chunks dari dokumen ini
    
    # ===== CONTENT =====
    filename = Column(String(255), index=True)
    content = Column(Text, nullable=False)
    
    # ===== METADATA =====
    metadata_json = Column(JSON, nullable=True)
    
    # ===== STATUS TRACKING =====
    # pending → embedded → (optional: deleted)
    status = Column(String(50), nullable=False, server_default="pending", index=True)
    
    # ===== TIMESTAMPS =====
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    embedded_at = Column(DateTime(timezone=True), nullable=True)  # Kapan di-embed
