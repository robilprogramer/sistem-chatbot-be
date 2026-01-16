# ============================================================================
# FILE: api/chat_router.py
# ============================================================================
"""
Chat Router dengan debugging capabilities

Endpoints:
- POST /chat - Main chat endpoint
- GET /chat/debug - Debug vectorstore
- POST /chat/test-retrieval - Test retrieval tanpa LLM
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import traceback

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rag_factory import (
    get_query_chain,
    get_retriever,
    inspect_vectorstore
)


# ============================================================================
# SCHEMAS
# ============================================================================
class ChatRequest(BaseModel):
    question: str
    verbose: bool = False
    
class ChatResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]
    metadata: Dict[str, Any]

class RetrievalTestRequest(BaseModel):
    query: str
    top_k: int = 5
    fetch_full_document: bool = True


# ============================================================================
# ROUTER
# ============================================================================
def create_chat_router(prefix: str = "/api/v1/chat") -> APIRouter:
    """Create chat router"""
    
    router = APIRouter(prefix=prefix, tags=["Chat"])
    
    @router.post("/", response_model=ChatResponse)
    async def chat(req: ChatRequest):
        """
        Main chat endpoint
        
        Flow:
        1. Get query chain (singleton)
        2. Execute RAG pipeline
        3. Return answer with sources
        """
        try:
            # Get singleton query chain
            query_chain = get_query_chain()
            
            # Execute RAG
            result = query_chain.query(
                question=req.question,
                verbose=req.verbose
            )
            
            return result
            
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/debug")
    async def debug_vectorstore():
        """
        Debug endpoint - inspect vectorstore
        
        Returns:
        - Total chunks
        - Unique documents
        - Sample metadata
        - Document ID list
        """
        try:
            info = inspect_vectorstore()
            return {
                "status": "ok",
                "vectorstore": info
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    @router.post("/test-retrieval")
    async def test_retrieval(req: RetrievalTestRequest):
        """
        Test retrieval tanpa LLM
        
        Berguna untuk debug:
        - Apakah chunks ter-retrieve dengan benar
        - Apakah document aggregation bekerja
        - Preview context yang akan dikirim ke LLM
        """
        try:
            retriever = get_retriever()
            
            # Temporarily override settings if needed
            original_fetch_full = retriever.fetch_full_document
            original_top_k = retriever.top_k
            
            retriever.fetch_full_document = req.fetch_full_document
            retriever.top_k = req.top_k
            
            # Retrieve
            docs = retriever.retrieve(req.query, verbose=True)
            
            # Restore settings
            retriever.fetch_full_document = original_fetch_full
            retriever.top_k = original_top_k
            
            # Build response
            results = []
            for doc in docs:
                results.append({
                    "document_id": doc.metadata.get('document_id', 'N/A'),
                    "source": doc.metadata.get('source', 'Unknown'),
                    "jenjang": doc.metadata.get('jenjang', ''),
                    "tahun": doc.metadata.get('tahun', ''),
                    "similarity_score": doc.metadata.get('similarity_score', 0),
                    "is_aggregated": doc.metadata.get('is_aggregated', False),
                    "merged_chunks": doc.metadata.get('merged_chunks', 1),
                    "content_length": len(doc.page_content),
                    "content_preview": doc.page_content[:500] + "..." if len(doc.page_content) > 500 else doc.page_content
                })
            
            return {
                "query": req.query,
                "settings": {
                    "top_k": req.top_k,
                    "fetch_full_document": req.fetch_full_document
                },
                "results_count": len(results),
                "results": results
            }
            
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/documents")
    async def list_documents():
        """
        List all unique documents in vectorstore
        """
        info = inspect_vectorstore()
        return {
            "total_documents": info.get("unique_documents", 0),
            "document_ids": info.get("document_ids", []),
            "sources": info.get("sources", [])
        }
    
    return router


# ============================================================================
# STANDALONE ROUTER (for direct import)
# ============================================================================
router = create_chat_router()
