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
from informasional.api.vectorstore_router import router as vectorstore_router
from informasional.api.chat_router import router as chat_router
from informasional.api.statistics_router import router as statistics_router
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
    
    # 4. Load dynamic config
    print("\n📋 Loading configuration...")
    try:
        from transaksional.app.config_loader import get_config_loader
        loader = get_config_loader()
        print(f"   ✅ Config source: {loader.source.value}")
        print(f"   ✅ Fallback: {loader.fallback.value}")
    except Exception as e:
        print(f"   ⚠️  Config loader warning: {e}")
    
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
    version="2.0.0",
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
app.include_router(vectorstore_router)
app.include_router(embedding_router)
app.include_router(statistics_router)
app.include_router(chat_router)


# =============================================================================
# TRANSACTIONAL CHATBOT ROUTERS
# =============================================================================

app.include_router(session_router)
app.include_router(transaksional_chat_router)
app.include_router(upload_router)
app.include_router(status_router)
app.include_router(config_router)
app.include_router(admin_router)


# =============================================================================
# HEALTH CHECK & INFO ENDPOINTS
# =============================================================================

@app.get("/", tags=["Health"])
async def root():
    """Root endpoint - API info"""
    return {
        "name": "YPI Al-Azhar Chatbot API",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "features": {
            "informational_chatbot": True,
            "transactional_chatbot": True,
            "multiple_upload": True,
            "auto_trigger": True,
            "rating_system": True,
            "dynamic_config": True
        }
    }
    
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.ico")


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    trigger_manager = get_trigger_manager()
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "database": "connected",
            "auto_trigger": {
                "running": trigger_manager._running,
                "active_sessions": len(trigger_manager._sessions),
                "triggers_configured": len(trigger_manager._triggers)
            }
        }
    }


@app.get("/stats", tags=["Health"])
async def get_stats():
    """Get system statistics"""
    trigger_manager = get_trigger_manager()
    rating_manager = get_rating_manager()
    
    trigger_stats = trigger_manager.get_stats()
    rating_stats = rating_manager.get_rating_stats()
    
    return {
        "timestamp": datetime.now().isoformat(),
        "auto_trigger": trigger_stats,
        "ratings": rating_stats
    }


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