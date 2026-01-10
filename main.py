import uvicorn
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Informational chatbot routers
from informasional.api.chunking_router import router as chunking_router
from informasional.api.vectorstore_router import router as vectorstore_router
from informasional.api.embeding_router import router as embedding_router
from informasional.api.chat_router import router as chat_router  
from informasional.api.document_router import router as document_router
from informasional.api.statistics_router import router as statistics_router
from informasional.utils.db import Base, engine

# Transactional chatbot routers
from transaksional.api.session_router import router as session_router
from transaksional.api.transaksional_chat_router import router as transaksional_chat_router
from transaksional.api.upload_router import router as upload_router
from transaksional.api.status_router import router as status_router
from transaksional.api.config_router import router as config_router
from transaksional.api.admin_router import router as admin_router
from transaksional.app.config import settings
from transaksional.app.database import init_database


app = FastAPI(
    title="YPI Al-Azhar Chatbot API",
    description="Sistem chatbot layanan informasi dan pendaftaran siswa baru YPI Al-Azhar",
    version="1.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Startup event
@app.on_event("startup")
async def startup():
    init_database()
    Base.metadata.create_all(bind=engine)
    print("✅ YPI Chatbot API Ready - Version 1.0.0")



# ============================================
# INFORMATIONAL CHATBOT ROUTERS
# ============================================
app.include_router(document_router)
app.include_router(chunking_router)        
app.include_router(vectorstore_router)    
app.include_router(embedding_router)      
app.include_router(statistics_router)
app.include_router(chat_router)

# ============================================
# TRANSACTIONAL CHATBOT ROUTERS
# ============================================
app.include_router(session_router)
app.include_router(transaksional_chat_router)
app.include_router(upload_router)
app.include_router(status_router)
app.include_router(config_router)
app.include_router(admin_router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.port)