"""
CS Agent Router - API endpoints khusus untuk CS Agent Dashboard

File: cs/cs_agent_router.py

ENDPOINTS:
- POST /cs/agent/login          : Login CS agent
- GET  /cs/agent/profile/{id}   : Get agent profile
- PUT  /cs/agent/status/{id}    : Update agent status
- GET  /cs/agent/sessions/{id}  : Get active sessions
- GET  /cs/agent/logout/{id}    : Logout agent
- GET  /cs/agent/stats          : Get CS statistics
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime

from .schemas import CSAgentStatus
from .session_manager import get_session_manager
from .websocket_manager import get_ws_manager


# Konfigurasi prefix - sesuaikan dengan project kamu
API_PREFIX = "/api/v1"

router = APIRouter(
    prefix=f"{API_PREFIX}/cs/agent",
    tags=["CS Agent"]
)


# ============================================================================
# SCHEMAS
# ============================================================================

class AgentLoginRequest(BaseModel):
    """Login request"""
    email: str
    password: str


class AgentLoginResponse(BaseModel):
    """Login response"""
    success: bool
    agent_id: str
    name: str
    token: Optional[str] = None
    message: str


class AgentProfileResponse(BaseModel):
    """Agent profile"""
    agent_id: str
    name: str
    email: str
    status: str
    current_sessions: int
    max_sessions: int


class AgentStatusUpdate(BaseModel):
    """Status update request"""
    status: CSAgentStatus


# ============================================================================
# MOCK DATA STORE (Development - Production pakai Database)
# ============================================================================

MOCK_AGENTS: Dict[str, dict] = {
    "cs001": {
        "agent_id": "cs001",
        "name": "Budi Santoso",
        "email": "budi@alazhar.sch.id",
        "password": "cs123",  # Production: HASH PASSWORD!
        "status": "offline",
        "current_sessions": 0,
        "max_sessions": 3
    },
    "cs002": {
        "agent_id": "cs002",
        "name": "Siti Aminah",
        "email": "siti@alazhar.sch.id",
        "password": "cs123",
        "status": "offline",
        "current_sessions": 0,
        "max_sessions": 3
    },
    "cs003": {
        "agent_id": "cs003",
        "name": "Ahmad Rizki",
        "email": "ahmad@alazhar.sch.id",
        "password": "cs123",
        "status": "offline",
        "current_sessions": 0,
        "max_sessions": 3
    }
}


def get_agent_by_email(email: str) -> Optional[dict]:
    """Find agent by email"""
    for agent in MOCK_AGENTS.values():
        if agent["email"] == email:
            return agent
    return None


def get_agent_by_id(agent_id: str) -> Optional[dict]:
    """Find agent by ID"""
    return MOCK_AGENTS.get(agent_id)


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/login", response_model=AgentLoginResponse)
async def agent_login(request: AgentLoginRequest):
    """
    Login untuk CS Agent
    
    Demo credentials:
    - budi@alazhar.sch.id / cs123
    - siti@alazhar.sch.id / cs123
    - ahmad@alazhar.sch.id / cs123
    """
    agent = get_agent_by_email(request.email)
    
    if not agent:
        raise HTTPException(status_code=401, detail="Email tidak ditemukan")
    
    if agent["password"] != request.password:
        raise HTTPException(status_code=401, detail="Password salah")
    
    # Update status to online
    agent["status"] = "online"
    
    return AgentLoginResponse(
        success=True,
        agent_id=agent["agent_id"],
        name=agent["name"],
        token=f"mock-token-{agent['agent_id']}-{int(datetime.now().timestamp())}",
        message=f"Selamat datang, {agent['name']}!"
    )


@router.get("/profile/{agent_id}", response_model=AgentProfileResponse)
async def get_agent_profile(agent_id: str):
    """Get agent profile"""
    agent = get_agent_by_id(agent_id)
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent tidak ditemukan")
    
    # Get actual session count from WebSocket manager
    ws_manager = get_ws_manager()
    current_sessions = ws_manager.get_agent_session_count(agent_id)
    
    return AgentProfileResponse(
        agent_id=agent["agent_id"],
        name=agent["name"],
        email=agent["email"],
        status=agent["status"],
        current_sessions=current_sessions,
        max_sessions=agent["max_sessions"]
    )


@router.put("/status/{agent_id}")
async def update_agent_status(agent_id: str, request: AgentStatusUpdate):
    """
    Update CS agent status
    
    Status options: online, busy, offline
    """
    agent = get_agent_by_id(agent_id)
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent tidak ditemukan")
    
    old_status = agent["status"]
    agent["status"] = request.status.value
    
    # Update WebSocket manager availability
    ws_manager = get_ws_manager()
    if request.status == CSAgentStatus.ONLINE:
        await ws_manager.set_agent_available(agent_id)
    else:
        await ws_manager.set_agent_busy(agent_id)
    
    return {
        "success": True,
        "agent_id": agent_id,
        "old_status": old_status,
        "new_status": request.status.value,
        "message": f"Status berubah dari {old_status} ke {request.status.value}"
    }


@router.get("/sessions/{agent_id}")
async def get_agent_sessions(agent_id: str):
    """Get semua active sessions yang di-handle agent"""
    agent = get_agent_by_id(agent_id)
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent tidak ditemukan")
    
    session_manager = get_session_manager()
    sessions = await session_manager.get_active_cs_sessions(agent_id)
    
    # Import history from router
    from .router import CHAT_HISTORIES
    
    result = []
    for session in sessions:
        history = CHAT_HISTORIES.get(session.session_id, [])
        last_message = history[-1]["content"][:50] + "..." if history else None
        
        result.append({
            "session_id": session.session_id,
            "user_id": session.user_id,
            "escalation_reason": session.escalation_reason.value if session.escalation_reason else None,
            "started_at": session.cs_connected_at.isoformat() if session.cs_connected_at else None,
            "message_count": len(history),
            "last_message_preview": last_message
        })
    
    return {
        "agent_id": agent_id,
        "total_sessions": len(result),
        "sessions": result
    }


@router.get("/logout/{agent_id}")
async def agent_logout(agent_id: str):
    """Logout CS agent"""
    agent = get_agent_by_id(agent_id)
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent tidak ditemukan")
    
    # Set offline
    agent["status"] = "offline"
    
    # Disconnect from WebSocket manager
    ws_manager = get_ws_manager()
    await ws_manager.set_agent_busy(agent_id)
    
    return {
        "success": True,
        "message": f"Sampai jumpa, {agent['name']}!"
    }


@router.get("/stats")
async def get_cs_stats():
    """Get CS system statistics"""
    session_manager = get_session_manager()
    ws_manager = get_ws_manager()
    
    # Count agents by status
    online_agents = sum(1 for a in MOCK_AGENTS.values() if a["status"] == "online")
    busy_agents = sum(1 for a in MOCK_AGENTS.values() if a["status"] == "busy")
    offline_agents = sum(1 for a in MOCK_AGENTS.values() if a["status"] == "offline")
    
    # Get queue info
    queue = await session_manager.get_queue()
    
    return {
        "agents": {
            "total": len(MOCK_AGENTS),
            "online": online_agents,
            "busy": busy_agents,
            "offline": offline_agents
        },
        "queue": {
            "waiting": len(queue),
            "items": queue[:10]  # First 10
        },
        "websocket": ws_manager.get_status(),
        "timestamp": datetime.now().isoformat()
    }


@router.get("/list")
async def list_all_agents():
    """List all CS agents (for admin)"""
    ws_manager = get_ws_manager()
    
    agents = []
    for agent in MOCK_AGENTS.values():
        agents.append({
            "agent_id": agent["agent_id"],
            "name": agent["name"],
            "email": agent["email"],
            "status": agent["status"],
            "current_sessions": ws_manager.get_agent_session_count(agent["agent_id"]),
            "max_sessions": agent["max_sessions"],
            "is_connected": ws_manager.is_cs_connected(agent["agent_id"])
        })
    
    return {"agents": agents, "total": len(agents)}