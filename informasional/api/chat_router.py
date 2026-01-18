"""
Chat Router - Main RAG Interface

ENDPOINTS:
- POST /chat/              : Main chat endpoint
- POST /chat/verbose       : Chat dengan verbose output
- POST /chat/test-retrieval: Test retrieval tanpa LLM
- GET  /chat/debug         : Get vectorstore info
- GET  /chat/check-aggregation/{doc_id}: Check document chunks

INTEGRASI:
- QueryChain (singleton)
- SmartRetriever (singleton)
- EmbeddingManager (singleton)
- VectorStoreManager (singleton)
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from informasional.core.rag_factory import get_query_chain, get_vectorstore_info
from transaksional.app.config import settings


# ============================================================================
# ROUTER SETUP
# ============================================================================
router = APIRouter(
    prefix=f"{settings.informational_prefix}/chat",
    tags=["Chat"]
)


# ============================================================================
# SCHEMAS
# ============================================================================
class ChatRequest(BaseModel):
    """Chat request schema"""
    question: str = Field(..., min_length=1, description="User question")
    filter: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata filter (e.g., {'jenjang': 'TK'})"
    )


class TestRetrievalRequest(BaseModel):
    """Test retrieval request schema"""
    query: str = Field(..., min_length=1)
    top_k: Optional[int] = Field(default=5, ge=1, le=20)
    filter: Optional[Dict[str, Any]] = None
    verbose: Optional[bool] = True


class ChatResponse(BaseModel):
    """Chat response schema"""
    answer: str
    sources: List[Dict[str, Any]]
    metadata: Dict[str, Any]


# ============================================================================
# MAIN CHAT ENDPOINT
# ============================================================================
@router.post("/", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Main Chat Endpoint - RAG Interface
    
    Flow:
    1. Retrieve relevant documents (dengan aggregation)
    2. Check relevance
    3. Generate answer via LLM
    
    Request:
        - question: str (user query)
        - filter: Optional dict (metadata filter)
    
    Response:
        - answer: str
        - sources: List[Dict]
        - metadata: Dict
    
    Example:
        POST /chat/
        {
            "question": "Berapa biaya SPP TK Al-Azhar?",
            "filter": {"jenjang": "TK"}
        }
    """
    try:
        # Get singleton query chain
        query_chain = get_query_chain()
        
        # Execute RAG pipeline (dengan document aggregation)
        result = query_chain.query(
            question=req.question,
            filter=req.filter,
            verbose=False
        )
        
        return ChatResponse(**result)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CHAT WITH VERBOSE (Debug)
# ============================================================================
@router.post("/verbose", response_model=ChatResponse)
async def chat_verbose(req: ChatRequest):
    """
    Chat dengan verbose output
    
    Sama dengan /chat/ tapi print debug info ke console
    """
    try:
        query_chain = get_query_chain()
        
        result = query_chain.query(
            question=req.question,
            filter=req.filter,
            verbose=True  # Print debug info
        )
        
        return ChatResponse(**result)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TEST RETRIEVAL (Without LLM)
# ============================================================================
@router.post("/test-retrieval")
async def test_retrieval(req: TestRetrievalRequest):
    """
    Test retrieval tanpa LLM
    
    Berguna untuk debug:
    - Apakah chunks ter-retrieve dengan benar
    - Apakah document aggregation bekerja
    - Preview context yang akan dikirim ke LLM
    
    Response:
        - query: str
        - results_count: int
        - results: List dengan document info dan content preview
    """
    try:
        query_chain = get_query_chain()
        retriever = query_chain.retriever
        
        # Override top_k jika berbeda
        original_top_k = retriever.top_k
        if req.top_k:
            retriever.top_k = req.top_k
        
        try:
            # Retrieve dengan verbose
            docs = retriever.retrieve(
                req.query,
                filter=req.filter,
                verbose=req.verbose
            )
        finally:
            # Restore original top_k
            retriever.top_k = original_top_k
        
        # Build response
        results = []
        for doc in docs:
            meta = doc.metadata
            results.append({
                "document_id": meta.get('document_id', 'N/A'),
                "source": meta.get('source', 'Unknown'),
                "jenjang": meta.get('jenjang', ''),
                "cabang": meta.get('cabang', ''),
                "tahun": meta.get('tahun', ''),
                "similarity_score": round(meta.get('similarity_score', 0), 4),
                "is_aggregated": meta.get('is_aggregated', False),
                "merged_chunks": meta.get('merged_chunks', 1),
                "content_length": len(doc.page_content),
                "content_preview": doc.page_content[:500] + "..." if len(doc.page_content) > 500 else doc.page_content
            })
        
        return {
            "query": req.query,
            "filter": req.filter,
            "results_count": len(results),
            "results": results
        }
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DEBUG: Vectorstore Info
# ============================================================================
@router.get("/debug")
async def debug_vectorstore():
    """
    Debug endpoint - Get vectorstore info
    
    Returns:
        - total_chunks: int
        - unique_documents: int
        - document_ids: List[str] (sample)
        - embedding info
    """
    try:
        info = get_vectorstore_info()
        
        # Get additional info from embedding manager
        query_chain = get_query_chain()
        embedding_info = query_chain.retriever.embedding_manager.get_info()
        
        return {
            "status": "ok",
            "vectorstore": info,
            "embedding": embedding_info
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


# ============================================================================
# DEBUG: Check Document Aggregation
# ============================================================================
@router.get("/check-aggregation/{document_id}")
async def check_document_aggregation(document_id: str):
    """
    Check apakah semua chunks untuk document_id bisa di-fetch
    
    Useful untuk verify document aggregation
    """
    try:
        query_chain = get_query_chain()
        retriever = query_chain.retriever
        
        # Fetch all chunks untuk document_id
        chunks = retriever._fetch_all_chunks(document_id)
        
        if not chunks:
            return {
                "document_id": document_id,
                "status": "not_found",
                "message": "No chunks found for this document_id"
            }
        
        return {
            "document_id": document_id,
            "status": "ok",
            "total_chunks": len(chunks),
            "expected_total": chunks[0].metadata.get('total_chunks', 'unknown'),
            "chunks": [
                {
                    "chunk_index": c.metadata.get('chunk_index', 0),
                    "chunk_id": c.metadata.get('chunk_id', 'N/A'),
                    "content_length": len(c.page_content),
                    "preview": c.page_content[:150] + "..." if len(c.page_content) > 150 else c.page_content
                }
                for c in chunks
            ]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DEBUG: List All Document IDs
# ============================================================================
@router.get("/documents")
async def list_documents(
    limit: int = Query(default=50, ge=1, le=200)
):
    """
    List semua document_ids yang ada di vectorstore
    """
    try:
        info = get_vectorstore_info()
        
        return {
            "total_vectors": info.get("total_vectors", 0),
            "unique_documents": info.get("unique_documents", 0),
            "document_ids": info.get("document_ids_sample", [])[:limit]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HEALTH CHECK
# ============================================================================
@router.get("/health")
async def health_check():
    """
    Health check endpoint
    
    Verifies:
    - QueryChain initialized
    - Vectorstore accessible
    - Embedding model loaded
    """
    try:
        query_chain = get_query_chain()
        info = query_chain.retriever.get_collection_info()
        
        return {
            "status": "healthy",
            "vectorstore": {
                "total_vectors": info.get("total_vectors", 0),
                "unique_documents": info.get("unique_documents", 0)
            },
            "embedding_model": query_chain.retriever.embedding_manager.model_name,
            "llm_ready": query_chain.llm is not None
        }
    
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }