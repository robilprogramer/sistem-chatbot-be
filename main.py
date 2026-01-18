import uvicorn
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Informational chatbot routers
from informasional.utils.db import Base, engine
from informasional.api.document_router import router as document_router
from informasional.api.chunking_router import router as chunking_router
from informasional.api.embeding_router import router as embedding_router
from informasional.api.chat_router import router as chat_router
from informasional.api.knowledgebase_router import router as knowledgebase_router
from informasional.api.quick_questions_router import router as quick_questions_router 
from informasional.models.master_cabang import MasterCabangModel
from informasional.models.master_jenjang import MasterJenjangModel
from informasional.models.master_kategori import MasterKategoriModel

# Transactional chatbot routers
from transaksional.api.session_router import router as session_router
from transaksional.api.transactional_chat_router_enhanced import router as transaksional_chat_router
from transaksional.api.upload_router import router as upload_router
from transaksional.api.status_router import router as status_router
from transaksional.api.config_router import router as config_router
from transaksional.api.admin_router import router as admin_router
# main.py
from transaksional.api.registration_router  import router  as registration_router
# Core modules
from transaksional.app.config import settings
from transaksional.app.database import init_database, get_db_manager

# New feature modules
from transaksional.app.auto_trigger import get_trigger_manager, init_trigger_manager
from transaksional.app.rating_system import init_rating_manager, get_rating_manager


# =============================================================================
# LIFESPAN (Modern way to handle startup/shutdown)
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown events using lifespan context manager.
    This is the modern way (FastAPI 0.93+) to handle app lifecycle.
    """
    # =========================================================================
    # STARTUP
    # =========================================================================
    print("\n" + "="*60)
    print("🚀 STARTING YPI Al-Azhar Chatbot API")
    print("="*60)
    
    # 1. Initialize database
    print("\n📦 Initializing database...")
    db = init_database()
    Base.metadata.create_all(bind=engine)
    print("   ✅ Database ready")
    
    # 2. Initialize auto-trigger system
    print("\n⏰ Initializing auto-trigger system...")
    trigger_manager = init_trigger_manager(db_manager=db)
    
    # Start background checker for idle detection
    if settings.app.get("idle_detection_enabled", True):
        trigger_manager.start_background_checker()
        print(f"   ✅ Background checker started (interval: {trigger_manager.check_interval}s)")
    else:
        print("   ⚠️  Idle detection disabled")
    
    # 3. Initialize rating system
    print("\n⭐ Initializing rating system...")
    rating_manager = init_rating_manager(db_manager=db)
    print("   ✅ Rating system ready")
    
    print("\n" + "="*60)
    print(f"✅ YPI Chatbot API Ready - Version {settings.app_version}")
    print(f"   Host: {settings.host}:{settings.port}")
    print(f"   Debug: {settings.debug}")
    print("="*60 + "\n")
    
    yield  # Application is running
    
    # =========================================================================
    # SHUTDOWN
    # =========================================================================
    print("\n" + "="*60)
    print("🛑 SHUTTING DOWN YPI Al-Azhar Chatbot API")
    print("="*60)
    
    # Stop background checker
    print("\n⏰ Stopping auto-trigger background checker...")
    trigger_manager = get_trigger_manager()
    trigger_manager.stop_background_checker()
    print("   ✅ Background checker stopped")
    print("\n✅ Shutdown complete\n")


# =============================================================================
# CREATE APP
# =============================================================================

app = FastAPI(
    title="YPI Al-Azhar Chatbot API",
    description="""
    Sistem chatbot layanan informasi dan pendaftaran siswa baru YPI Al-Azhar.
    
    ## Features
    - 📚 Informational Chatbot (RAG-based Q&A)
    - 📝 Transactional Chatbot (Student Registration)
    - 📤 Multiple File Upload
    - ⏰ Auto-trigger Messages (Idle Detection)
    - ⭐ Rating System
    - 🔄 Dynamic Config (YAML/Database)
    """,
    version="1.0.0",
    lifespan=lifespan
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# =============================================================================
# CORS Middleware
# =============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# INFORMATIONAL CHATBOT ROUTERS
# =============================================================================

app.include_router(document_router)
app.include_router(chunking_router)
app.include_router(embedding_router)
app.include_router(chat_router)
app.include_router(knowledgebase_router) 
app.include_router(quick_questions_router) 


# =============================================================================
# TRANSACTIONAL CHATBOT ROUTERS
# =============================================================================

app.include_router(session_router)
app.include_router(transaksional_chat_router)
app.include_router(upload_router)
app.include_router(status_router)
app.include_router(config_router)
app.include_router(admin_router)
app.include_router(registration_router)

    
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.ico")


# =============================================================================
# RUN APPLICATION
# =============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info"
    )