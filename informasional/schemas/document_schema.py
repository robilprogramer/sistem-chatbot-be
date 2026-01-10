# app/schemas/document_schema.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ExtractionMethod(str, Enum):
    NATIVE = "native"
    OCR = "ocr"
    HYBRID = "hybrid"

# Response Schemas
class DocumentBase(BaseModel):
    original_filename: str
    file_size: int
    mime_type: str

class DocumentCreate(DocumentBase):
    filename: str
    file_path: str

class DocumentResponse(DocumentBase):
    id: int
    filename: str
    total_pages: Optional[int]
    is_scanned: Optional[bool]
    extraction_method: Optional[ExtractionMethod]
    text_length: Optional[int]
    status: DocumentStatus
    ocr_confidence: Optional[float]
    extraction_duration: Optional[float]
    created_at: datetime
    updated_at: Optional[datetime]
    processed_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class DocumentDetailResponse(DocumentResponse):
    raw_text: Optional[str]
    tables_data: Optional[List[Dict]]
    images_data: Optional[List[Dict]]
    layout_info: Optional[Dict]
    error_message: Optional[str]
    metadata: Optional[Dict]
    
    class Config:
        from_attributes = True

class DocumentListResponse(BaseModel):
    total: int
    documents: List[DocumentResponse]
    page: int
    page_size: int
    total_pages: int

class DocumentUploadResponse(BaseModel):
    success: bool
    message: str
    document_id: Optional[int]
    filename: Optional[str]
    status: Optional[str]

class DocumentProcessResponse(BaseModel):
    success: bool
    message: str
    document_id: int
    raw_text_preview: Optional[str]  # First 500 chars
    total_pages: Optional[int]
    text_length: Optional[int]
    tables_count: Optional[int]
    images_count: Optional[int]
    
class DocumentRawTextUpdateRequest(BaseModel):
    raw_text: str = Field(..., description="Updated raw text content")    