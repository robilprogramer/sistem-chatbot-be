from pydantic import BaseModel
from typing import List, Optional, Dict,Any

class ChunkResponse(BaseModel):
    id: Optional[int] = None
    content: str
    metadata: Optional[Dict]

class ChunkUpdateRequest(BaseModel):
    content: str
    metadata: Dict[str, Any]
class ChunkingRequestDocument(BaseModel):
    filename: str
    content: str

class ChunkingRequest(BaseModel):
    documents: List[ChunkingRequestDocument]

class ChunkingResponse(BaseModel):
    total_chunks: int
    chunks: List[ChunkResponse]

class StandardResponse(BaseModel):
    status_code: int
    message: str
    data: Optional[Any] = None
    
class ChatRequest(BaseModel):
    """
    Request body untuk endpoint /chat
    """
    question: str
    session_id: Optional[str] = None
    metadata_filter: Optional[Dict[str, Any]] = None


class SourceDocument(BaseModel):
    """
    Sumber dokumen yang dipakai untuk menjawab
    """
    jenjang: Optional[str]
    cabang: Optional[str]
    tahun: Optional[str]
    content: Optional[str] = None


class ChatResponse(BaseModel):
    """
    Response endpoint /chat
    """
    answer: str
    sources: List[SourceDocument]
    
class ChunkBulkUpdateItem(BaseModel):
    id: int
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class ChunkBulkUpdateRequest(BaseModel):
    chunks: List[ChunkBulkUpdateItem]    