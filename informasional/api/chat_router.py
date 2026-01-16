from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from informasional.schemas.chunking_schema import ChatRequest
from informasional.core.rag_factory import get_query_chain, get_vectorstore_info
from transaksional.app.config import settings
router = APIRouter(prefix=f"{settings.informational_prefix}/chat", tags=["Chat"])


# ==============================
# Schemas
# ==============================
class TestRetrievalRequest(BaseModel):
    query: str
    top_k: Optional[int] = 5
    verbose: Optional[bool] = True


# ==============================
# Main Chat Endpoint
# ==============================
@router.post("/")
async def chat(req: ChatRequest):
    """
    Chat endpoint - Main RAG interface
    
    Request:
        - question: str (user query)
    
    Response:
        - answer: str
        - sources: List[Dict]
        - metadata: Dict
    """
    try:
        # Get singleton query chain
        query_chain = get_query_chain()
        
        # Execute RAG pipeline (dengan document aggregation)
        result = query_chain.query(req.question, verbose=False)
        
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ==============================
# Debug: Chat with verbose
# ==============================
@router.post("/verbose")
async def chat_verbose(req: ChatRequest):
    """
    Chat with verbose output (untuk debugging)
    """
    try:
        query_chain = get_query_chain()
        result = query_chain.query(req.question, verbose=True)
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ==============================
# Debug: Vectorstore Info
# ==============================
@router.get("/debug")
async def debug_vectorstore():
    """
    Debug endpoint - Get vectorstore info
    
    Returns:
        - total_chunks: int
        - unique_documents: int
        - document_ids: List[str]
    """
    try:
        info = get_vectorstore_info()
        return {
            "status": "ok",
            "vectorstore": info
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


# ==============================
# Debug: Test Retrieval (tanpa LLM)
# ==============================
@router.post("/test-retrieval")
async def test_retrieval(req: TestRetrievalRequest):
    """
    Test retrieval tanpa LLM
    
    Berguna untuk debug:
    - Apakah chunks ter-retrieve dengan benar
    - Apakah document aggregation bekerja
    - Preview context yang akan dikirim ke LLM
    """
    try:
        query_chain = get_query_chain()
        retriever = query_chain.retriever
        
        # Retrieve dengan verbose
        docs = retriever.retrieve(req.query, verbose=req.verbose)
        
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
            "results_count": len(results),
            "results": results
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ==============================
# Debug: Check Document Aggregation
# ==============================
@router.get("/check-aggregation/{document_id}")
async def check_document_aggregation(document_id: str):
    """
    Check apakah semua chunks untuk document_id bisa di-fetch
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
            "chunks": [
                {
                    "chunk_index": c.metadata.get('chunk_index', 0),
                    "chunk_id": c.metadata.get('chunk_id', 'N/A'),
                    "content_length": len(c.page_content),
                    "preview": c.page_content[:100] + "..."
                }
                for c in chunks
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))