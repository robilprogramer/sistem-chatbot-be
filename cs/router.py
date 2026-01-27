"""
CS Router - WebSocket endpoints dan CS management APIs

File: cs/router.py

ENDPOINTS:
- WS  /cs/ws/user/{user_id}     : WebSocket untuk user
- WS  /cs/ws/agent/{agent_id}   : WebSocket untuk CS agent
- GET /cs/queue                  : Get current queue
- GET /cs/session/{user_id}      : Get session info
- POST /cs/session/{id}/close    : Close session
- GET /cs/status                 : Get CS system status
- GET /cs/history/{session_id}   : Get chat history
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from typing import Optional, Dict, List
from datetime import datetime

from .schemas import ChatMode
from .session_manager import get_session_manager
from .websocket_manager import get_ws_manager


# Konfigurasi prefix - sesuaikan dengan project kamu
API_PREFIX = "/api/v1"
router = APIRouter(
    prefix=f"{API_PREFIX}/cs",
    tags=["Customer Service"]
)


# ============================================================================
# IN-MEMORY CHAT HISTORY (Development - Production pakai database)
# ============================================================================

CHAT_HISTORIES: Dict[str, List[dict]] = {}


def save_message(session_id: str, sender_type: str, content: str, agent_id: str = None):
    """Save message to history"""
    if session_id not in CHAT_HISTORIES:
        CHAT_HISTORIES[session_id] = []
    
    CHAT_HISTORIES[session_id].append({
        "id": f"msg-{len(CHAT_HISTORIES[session_id]) + 1}-{int(datetime.now().timestamp() * 1000)}",
        "sender_type": sender_type,
        "content": content,
        "agent_id": agent_id,
        "timestamp": datetime.now().isoformat()
    })


# ============================================================================
# WEBSOCKET: USER CONNECTION
# ============================================================================

@router.websocket("/ws/user/{user_id}")
async def user_websocket(websocket: WebSocket, user_id: str):
    """
    WebSocket untuk user (ketika chat dengan CS)
    
    Messages FROM user:
        {"type": "message", "content": "..."}
    
    Messages TO user:
        {"type": "cs_assigned", "agent_id": "...", "agent_name": "...", "message": "..."}
        {"type": "cs_message", "content": "...", "agent_id": "..."}
        {"type": "queue_update", "position": N}
        {"type": "session_closed", "message": "..."}
    """
    ws_manager = get_ws_manager()
    session_manager = get_session_manager()
    
    await ws_manager.connect_user(websocket, user_id)
    
    try:
        # Get current session
        session = await session_manager.get_session(user_id)
        
        # Send queue position if pending
        if session and session.mode == ChatMode.PENDING_CS:
            position = await session_manager.get_queue_position(session.session_id)
            await ws_manager.send_to_user(user_id, {
                "type": "queue_update",
                "position": position
            })
        
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "message":
                content = data.get("content", "")
                
                # Get current session
                session = await session_manager.get_session(user_id)
                
                if session and session.mode == ChatMode.CS and session.cs_agent_id:
                    # Save to history
                    save_message(session.session_id, "user", content)
                    
                    # Forward to CS agent
                    await ws_manager.send_to_cs(session.cs_agent_id, {
                        "type": "user_message",
                        "session_id": session.session_id,
                        "user_id": user_id,
                        "content": content,
                        "timestamp": datetime.now().isoformat()
                    })
    
    except WebSocketDisconnect:
        await ws_manager.disconnect_user(user_id)
        print(f"🔌 User {user_id} disconnected from WebSocket")


# ============================================================================
# WEBSOCKET: CS AGENT CONNECTION
# ============================================================================

@router.websocket("/ws/agent/{agent_id}")
async def cs_agent_websocket(websocket: WebSocket, agent_id: str):
    """
    WebSocket untuk CS Agent
    
    Messages FROM agent:
        {"type": "accept_session", "session_id": "..."}
        {"type": "message", "session_id": "...", "content": "..."}
        {"type": "close_session", "session_id": "..."}
        {"type": "set_status", "status": "online|busy|offline"}
    
    Messages TO agent:
        {"type": "new_escalation", "session_id": "...", "user_id": "...", "reason": "..."}
        {"type": "user_message", "session_id": "...", "user_id": "...", "content": "..."}
        {"type": "queue_update", "queue": [...]}
    """
    ws_manager = get_ws_manager()
    session_manager = get_session_manager()
    
    await ws_manager.connect_cs(websocket, agent_id)
    
    # Send current queue
    queue = await session_manager.get_queue()
    await ws_manager.send_to_cs(agent_id, {
        "type": "queue_update",
        "queue": queue
    })
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            # -----------------------------------------------------------------
            # ACCEPT SESSION
            # -----------------------------------------------------------------
            if msg_type == "accept_session":
                session_id = data.get("session_id")
                
                # Get agent name from somewhere (simplified)
                agent_name = f"CS Agent {agent_id[-3:]}"
                
                session = await session_manager.assign_cs_to_session(
                    session_id, agent_id, agent_name
                )
                
                if session:
                    # Notify user
                    await ws_manager.send_to_user(session.user_id, {
                        "type": "cs_assigned",
                        "agent_id": agent_id,
                        "agent_name": agent_name,
                        "message": "Customer Service telah terhubung. Silakan lanjutkan percakapan Anda."
                    })
                    
                    # Track assignment
                    await ws_manager.assign_session_to_agent(agent_id, session_id)
                    
                    # Add system message
                    save_message(session_id, "system", f"{agent_name} bergabung ke sesi")
                    
                    # Update queue for all CS
                    queue = await session_manager.get_queue()
                    await ws_manager.broadcast_to_all_cs({
                        "type": "queue_update",
                        "queue": queue
                    })
                    
                    print(f"✅ Session {session_id} assigned to {agent_id}")
            
            # -----------------------------------------------------------------
            # SEND MESSAGE TO USER
            # -----------------------------------------------------------------
            elif msg_type == "message":
                session_id = data.get("session_id")
                content = data.get("content", "")
                
                session = await session_manager.get_session_by_id(session_id)
                if session:
                    # Save to history
                    save_message(session_id, "cs", content, agent_id)
                    
                    # Send to user
                    await ws_manager.send_to_user(session.user_id, {
                        "type": "cs_message",
                        "content": content,
                        "agent_id": agent_id,
                        "timestamp": datetime.now().isoformat()
                    })
            
            # -----------------------------------------------------------------
            # CLOSE SESSION
            # -----------------------------------------------------------------
            elif msg_type == "close_session":
                session_id = data.get("session_id")
                session = await session_manager.close_cs_session(session_id)
                
                if session:
                    # Add system message
                    save_message(session_id, "system", "Sesi ditutup oleh CS")
                    
                    # Notify user
                    await ws_manager.send_to_user(session.user_id, {
                        "type": "session_closed",
                        "message": "Sesi dengan Customer Service telah berakhir. Terima kasih telah menghubungi kami!"
                    })
                    
                    # Remove from agent's sessions
                    await ws_manager.remove_session_from_agent(agent_id, session_id)
                    
                    print(f"✅ Session {session_id} closed by {agent_id}")
            
            # -----------------------------------------------------------------
            # SET STATUS
            # -----------------------------------------------------------------
            elif msg_type == "set_status":
                status = data.get("status")
                if status == "online":
                    await ws_manager.set_agent_available(agent_id)
                elif status in ["busy", "offline"]:
                    await ws_manager.set_agent_busy(agent_id)
    
    except WebSocketDisconnect:
        await ws_manager.disconnect_cs(agent_id)
        print(f"🔌 CS Agent {agent_id} disconnected from WebSocket")


# ============================================================================
# REST APIs
# ============================================================================

@router.get("/queue")
async def get_queue():
    """Get current CS queue"""
    session_manager = get_session_manager()
    queue = await session_manager.get_queue()
    return {"queue": queue, "total": len(queue)}


@router.get("/session/{user_id}")
async def get_session_info(user_id: str):
    """Get session info for user"""
    session_manager = get_session_manager()
    session = await session_manager.get_session(user_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return session.to_dict()


@router.post("/escalate/{user_id}")
async def escalate_to_cs(user_id: str, reason: str = "explicit_request"):
    """
    Escalate user to CS queue
    
    Called by chat_router when escalation detected
    """
    from .schemas import EscalationReason
    
    session_manager = get_session_manager()
    ws_manager = get_ws_manager()
    
    # Get or create session
    session = await session_manager.get_or_create_session(user_id)
    
    # Map reason string to enum
    reason_map = {
        "explicit_request": EscalationReason.EXPLICIT_REQUEST,
        "low_confidence": EscalationReason.LOW_CONFIDENCE,
        "loop_detected": EscalationReason.LOOP_DETECTED,
        "sentiment_negative": EscalationReason.SENTIMENT_NEGATIVE,
    }
    escalation_reason = reason_map.get(reason, EscalationReason.EXPLICIT_REQUEST)
    
    # Escalate
    session = await session_manager.escalate_to_cs(user_id, escalation_reason)
    
    if session:
        # Notify CS agents
        await ws_manager.notify_new_escalation(
            session.session_id,
            user_id,
            reason
        )
        
        return {
            "success": True,
            "session_id": session.session_id,
            "queue_position": session.queue_position,
            "estimated_wait_time": session.queue_position * 2  # 2 min per position estimate
        }
    
    raise HTTPException(status_code=500, detail="Failed to escalate")


@router.post("/session/{session_id}/close")
async def close_session(session_id: str):
    """Close a CS session (return to bot mode)"""
    session_manager = get_session_manager()
    ws_manager = get_ws_manager()
    
    session = await session_manager.close_cs_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Notify user
    await ws_manager.send_to_user(session.user_id, {
        "type": "session_closed",
        "message": "Sesi telah berakhir."
    })
    
    return {"status": "closed", "session_id": session_id}


@router.post("/cancel/{user_id}")
async def cancel_cs_request(user_id: str):
    """Cancel CS request and return to bot mode"""
    session_manager = get_session_manager()
    
    session = await session_manager.cancel_cs_request(user_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {"status": "cancelled", "mode": session.mode.value}


@router.get("/status")
async def get_cs_status():
    """Get CS system status"""
    ws_manager = get_ws_manager()
    session_manager = get_session_manager()
    
    queue = await session_manager.get_queue()
    pending = await session_manager.get_pending_sessions()
    ws_status = ws_manager.get_status()
    
    return {
        "available": ws_status["available_cs_agents"] > 0,
        "available_agents": ws_status["available_cs_agents"],
        "connected_agents": ws_status["connected_cs_agents"],
        "queue_length": len(queue),
        "pending_sessions": len(pending),
        "estimated_wait_time": len(queue) * 2,  # 2 min per queue position
        "websocket": ws_status,
        "timestamp": datetime.now().isoformat()
    }


@router.get("/history/{session_id}")
async def get_chat_history(session_id: str, limit: int = 50):
    """Get chat history for a session"""
    history = CHAT_HISTORIES.get(session_id, [])
    
    return {
        "session_id": session_id,
        "total_messages": len(history),
        "messages": history[-limit:]
    }