# ============================================================================
# FILE: main.py
# ============================================================================
"""
Main FastAPI Application

Endpoints:
- /api/v1/chat - Chat dengan RAG
- /api/v1/ingest - Ingestion pipeline
- /api/v1/embed - Embedding operations (optional)
- /debug - Debug endpoints
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Local imports
from api.chat_router import create_chat_router
from api.ingestion_router import create_ingestion_router
from core.rag_factory import inspect_vectorstore, get_query_chain

# ============================================================================
# APP
# ============================================================================
app = FastAPI(
    title="YPI Al-Azhar RAG API",
    description="RAG API dengan Document Aggregation untuk YPI Al-Azhar",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# ROUTERS
# ============================================================================
chat_router = create_chat_router(prefix="/api/v1/chat")
ingest_router = create_ingestion_router(prefix="/api/v1/ingest")

app.include_router(chat_router)
app.include_router(ingest_router)


# ============================================================================
# ROOT ENDPOINTS
# ============================================================================
@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "ok",
        "service": "YPI Al-Azhar RAG API",
        "version": "2.0.0",
        "features": [
            "Document Aggregation",
            "Smart Retrieval",
            "Consistent document_id tracking"
        ]
    }

@app.get("/health")
async def health():
    """Health check dengan vectorstore status"""
    try:
        info = inspect_vectorstore()
        return {
            "status": "healthy",
            "vectorstore": {
                "total_chunks": info.get("total_chunks", 0),
                "unique_documents": info.get("unique_documents", 0)
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

@app.on_event("startup")
async def startup():
    """Initialize RAG on startup"""
    print("\n" + "="*60)
    print("🚀 Starting YPI Al-Azhar RAG API")
    print("="*60)
    
    # Pre-initialize query chain
    try:
        get_query_chain()
    except Exception as e:
        print(f"⚠️ Warning: Could not initialize RAG: {e}")
        print("   RAG will be initialized on first request")


# ============================================================================
# RUN
# ============================================================================
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
