# ============================================================================
# FILE: informasional/schemas/embedding_schema.py
# ============================================================================
"""
Pydantic schemas untuk Embedding API
"""

from pydantic import BaseModel
from typing import Any, Optional, Dict, List


class StandardResponse(BaseModel):
    """Standard API response wrapper"""
    status_code: int = 200
    message: str
    data: Optional[Any] = None


class EmbeddingStatsResponse(BaseModel):
    """Embedding statistics response"""
    postgresql: Dict[str, int]
    chromadb: Dict[str, Any]
    sync_status: str
    embedding_config: Dict[str, Any]


class VectorStoreInfoResponse(BaseModel):
    """VectorStore info response"""
    collection_name: str
    total_vectors: int
    unique_documents: int
    document_ids_sample: List[str]
    distance_function: str
    embedding_model: str
    embedding_dimension: int


class ReembedRequest(BaseModel):
    """Request untuk re-embed chunks"""
    chunk_ids: List[int]