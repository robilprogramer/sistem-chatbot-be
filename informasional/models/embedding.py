from sqlalchemy import Column, Integer, ForeignKey, JSON, DateTime
from sqlalchemy.sql import func
from informasional.utils.db import Base

class EmbeddingModel(Base):
    __tablename__ = "document_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    chunk_id = Column(Integer, ForeignKey("document_chunks.id"), nullable=False)
    vector = Column(JSON, nullable=False)  # simpan embedding sebagai JSON/array
    created_at = Column(DateTime(timezone=True), server_default=func.now())
