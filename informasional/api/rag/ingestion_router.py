# ============================================================================
# FILE: api/ingestion_router.py
# ============================================================================
"""
Ingestion Router - Pipeline untuk dokumen ke VectorStore

Flow:
1. Upload dokumen (content + metadata)
2. Chunk dengan document_id yang konsisten
3. Embed dan store ke ChromaDB
4. Return statistics

Endpoints:
- POST /ingest/document - Ingest single document
- POST /ingest/batch - Ingest multiple documents
- DELETE /ingest/document/{document_id} - Delete document
- GET /ingest/status - Get ingestion status
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import traceback
import json

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rag_factory import (
    get_chunker,
    get_vectorstore,
    inspect_vectorstore
)
from utils.enhanced_chunker import DocumentProcessor


# ============================================================================
# SCHEMAS
# ============================================================================
class DocumentInput(BaseModel):
    content: str
    metadata: Dict[str, Any]
    
class BatchInput(BaseModel):
    documents: List[DocumentInput]

class IngestResponse(BaseModel):
    status: str
    message: str
    document_id: Optional[str] = None
    total_chunks: int = 0
    details: Optional[Dict[str, Any]] = None


# ============================================================================
# ROUTER
# ============================================================================
def create_ingestion_router(prefix: str = "/api/v1/ingest") -> APIRouter:
    """Create ingestion router"""
    
    router = APIRouter(prefix=prefix, tags=["Ingestion"])
    
    @router.post("/document", response_model=IngestResponse)
    async def ingest_document(doc: DocumentInput):
        """
        Ingest single document
        
        Flow:
        1. Validate input
        2. Chunk document (dengan document_id)
        3. Add to vectorstore
        4. Return stats
        """
        try:
            # Get components
            chunker = get_chunker()
            vectorstore = get_vectorstore()
            
            # Chunk document
            chunks = chunker.chunk_document(
                content=doc.content,
                metadata=doc.metadata
            )
            
            if not chunks:
                return IngestResponse(
                    status="warning",
                    message="No content to process",
                    total_chunks=0
                )
            
            # Get document_id dari first chunk
            document_id = chunks[0].metadata.get('document_id', 'unknown')
            
            # Prepare IDs
            chunk_ids = [c.metadata['chunk_id'] for c in chunks]
            
            # Add to vectorstore
            vectorstore.add_documents(
                documents=chunks,
                ids=chunk_ids
            )
            
            return IngestResponse(
                status="success",
                message=f"Document ingested successfully",
                document_id=document_id,
                total_chunks=len(chunks),
                details={
                    "chunk_ids": chunk_ids,
                    "metadata": doc.metadata
                }
            )
            
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.post("/batch", response_model=IngestResponse)
    async def ingest_batch(batch: BatchInput):
        """
        Ingest multiple documents
        """
        try:
            chunker = get_chunker()
            vectorstore = get_vectorstore()
            
            all_chunks = []
            doc_ids = []
            
            for doc in batch.documents:
                chunks = chunker.chunk_document(
                    content=doc.content,
                    metadata=doc.metadata
                )
                
                if chunks:
                    all_chunks.extend(chunks)
                    doc_ids.append(chunks[0].metadata.get('document_id'))
            
            if not all_chunks:
                return IngestResponse(
                    status="warning",
                    message="No content to process",
                    total_chunks=0
                )
            
            # Add all chunks
            chunk_ids = [c.metadata['chunk_id'] for c in all_chunks]
            vectorstore.add_documents(
                documents=all_chunks,
                ids=chunk_ids
            )
            
            return IngestResponse(
                status="success",
                message=f"Batch ingested successfully",
                total_chunks=len(all_chunks),
                details={
                    "document_ids": list(set(doc_ids)),
                    "total_documents": len(set(doc_ids))
                }
            )
            
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.delete("/document/{document_id}")
    async def delete_document(document_id: str):
        """
        Delete all chunks for a document
        """
        try:
            vectorstore = get_vectorstore()
            collection = vectorstore._collection
            
            # Get all chunks with this document_id
            results = collection.get(
                where={"document_id": document_id},
                include=[]
            )
            
            if not results['ids']:
                raise HTTPException(
                    status_code=404,
                    detail=f"Document not found: {document_id}"
                )
            
            # Delete
            vectorstore.delete(ids=results['ids'])
            
            return {
                "status": "success",
                "message": f"Document deleted",
                "document_id": document_id,
                "deleted_chunks": len(results['ids'])
            }
            
        except HTTPException:
            raise
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/status")
    async def get_status():
        """
        Get current ingestion status
        """
        info = inspect_vectorstore()
        return {
            "status": "ok",
            "vectorstore": {
                "total_chunks": info.get("total_chunks", 0),
                "unique_documents": info.get("unique_documents", 0),
                "document_ids": info.get("document_ids", []),
                "jenjang_distribution": info.get("jenjang_distribution", {})
            }
        }
    
    @router.get("/document/{document_id}/chunks")
    async def get_document_chunks(document_id: str):
        """
        Get all chunks for a specific document
        """
        try:
            vectorstore = get_vectorstore()
            collection = vectorstore._collection
            
            # Get all chunks
            results = collection.get(
                where={"document_id": document_id},
                include=["documents", "metadatas"]
            )
            
            if not results['ids']:
                raise HTTPException(
                    status_code=404,
                    detail=f"Document not found: {document_id}"
                )
            
            # Sort by chunk_index
            chunks = []
            for i, (chunk_id, content, metadata) in enumerate(zip(
                results['ids'],
                results['documents'],
                results['metadatas']
            )):
                chunks.append({
                    "chunk_id": chunk_id,
                    "chunk_index": metadata.get('chunk_index', i),
                    "content_preview": content[:200] + "..." if len(content) > 200 else content,
                    "content_length": len(content),
                    "metadata": metadata
                })
            
            # Sort
            chunks.sort(key=lambda x: x['chunk_index'])
            
            return {
                "document_id": document_id,
                "total_chunks": len(chunks),
                "chunks": chunks
            }
            
        except HTTPException:
            raise
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    
    return router


# ============================================================================
# STANDALONE ROUTER
# ============================================================================
router = create_ingestion_router()
