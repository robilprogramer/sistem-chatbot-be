from fastapi import APIRouter, HTTPException
from informasional.schemas.chunking_schema import ChatRequest
from informasional.core.rag_factory import get_query_chain
from transaksional.app.config import settings
router = APIRouter(prefix=f"{settings.informational_prefix}/chat", tags=["Chat"])

@router.post("/")
async def chat(req: ChatRequest):
    """
    Chat endpoint - Simple interface
    
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
        
        # Execute RAG pipeline
        result = query_chain.query(req.question)
        
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))