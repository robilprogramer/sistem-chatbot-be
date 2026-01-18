# ============================================================================
# FILE: informasional/schemas/chunking_schema.py
# ============================================================================
"""
Pydantic schemas untuk Chunking API
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class ChunkResponse(BaseModel):
    """Single chunk response"""
    id: int
    content: str
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


class StandardResponse(BaseModel):
    """Standard API response wrapper"""
    status_code: int = 200
    message: str
    data: Optional[Any] = None
    
    class Config:
        from_attributes = True


class ChunkingResponse(BaseModel):
    """Response untuk chunking operation"""
    total_chunks: int
    chunks: List[ChunkResponse]


# ============================================================================
# REQUEST SCHEMAS (Simplified)
# ============================================================================

class ChunkingRequest(BaseModel):
    """Request untuk manual chunking (legacy support)"""
    documents: List["DocumentInput"]


class DocumentInput(BaseModel):
    """Single document input untuk chunking"""
    filename: str
    content: Optional[str] = ""  # Optional, bisa diambil dari DB
    metadata: Optional[Dict[str, Any]] = None

class ChunkUpdateRequest(BaseModel):
    content: str
    metadata: Dict[str, Any]
# Update forward reference
ChunkingRequest.model_rebuild()