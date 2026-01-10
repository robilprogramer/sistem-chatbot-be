from sqlalchemy import Column, Integer, Text, String, JSON, DateTime
from sqlalchemy.sql import func
from informasional.utils.db import Base


class ChunkModel(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)

    filename = Column(String(255), index=True)
    content = Column(Text, nullable=False)

    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Tambahkan status dengan default 'pending'
    status = Column(String(50), nullable=False, server_default="pending")
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),      # default saat insert
        onupdate=func.now()             # otomatis update saat row diubah
    )
