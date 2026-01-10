
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Float, Boolean, Enum
from sqlalchemy.sql import func
from informasional.utils.db import Base
import enum

class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ExtractionMethod(str, enum.Enum):
    NATIVE = "native"
    OCR = "ocr"
    HYBRID = "hybrid"


class Document(Base):
    __tablename__ = "documents"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # File Information
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)  # in bytes
    mime_type = Column(String(100), nullable=False)
    
    # Document Metadata
    total_pages = Column(Integer, nullable=True)
    is_scanned = Column(Boolean, default=False)
    extraction_method = Column(Enum(ExtractionMethod), nullable=True)
    
    # Extracted Content (RAW TEXT GABUNGAN SEMUA PAGE)
    raw_text = Column(Text, nullable=True)  # Full text dari semua pages
    text_length = Column(Integer, nullable=True)
    
    # Structured Data
    tables_data = Column(JSON, nullable=True)  # All tables from all pages
    images_data = Column(JSON, nullable=True)  # All images metadata
    layout_info = Column(JSON, nullable=True)  # Document structure info
    
    # Extraction Quality Metrics
    ocr_confidence = Column(Float, nullable=True)
    extraction_duration = Column(Float, nullable=True)  # in seconds
    
    # Processing Status
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False)
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Additional metadata
    extra_metadata = Column("metadata", JSON, nullable=True)
    
    def __repr__(self):
        return f"<Document {self.id}: {self.original_filename}>"


class DocumentPage(Base):
    """
    Optional: Untuk menyimpan detail per-page jika diperlukan
    """
    __tablename__ = "document_pages"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    
    # Page content
    text = Column(Text, nullable=True)
    tables = Column(JSON, nullable=True)
    images = Column(JSON, nullable=True)
    layout = Column(JSON, nullable=True)
    
    # Page metrics
    ocr_confidence = Column(Float, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<DocumentPage doc_id={self.document_id} page={self.page_number}>"