"""
WebSocket Manager - Manage WebSocket connections untuk User dan CS Agent

File: cs/websocket_manager.py
"""

from typing import Dict, Set, Optional, Any
from fastapi import WebSocket
import asyncio
import json


class WebSocketManager:
    """
    Manages WebSocket connections untuk:
    - Users (chat dengan CS)
    - CS Agents (handle multiple users)
    
    Features:
    - Track active connections
    - Send messages to specific user/agent
    - Broadcast to available CS agents
    - Track agent availability
    """
    
    def __init__(self):
        # User connections: user_id -> WebSocket
        self._user_connections: Dict[str, WebSocket] = {}
        
        # CS Agent connections: agent_id -> WebSocket
        self._cs_connections: Dict[str, WebSocket] = {}
        
        # Available CS agents (online and ready)
        self._available_cs: Set[str] = set()
        
        # Agent to sessions mapping: agent_id -> Set[session_id]
        self._agent_sessions: Dict[str, Set[str]] = {}
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
    
    # =========================================================================
    # USER CONNECTION MANAGEMENT
    # =========================================================================
    
    async def connect_user(self, websocket: WebSocket, user_id: str):
        """Accept and store user WebSocket connection"""
        await websocket.accept()
        async with self._lock:
            # Close existing connection if any
            if user_id in self._user_connections:
                try:
                    await self._user_connections[user_id].close()
                except:
                    pass
            self._user_connections[user_id] = websocket
        print(f"🟢 User {user_id} connected via WebSocket")
    
    async def disconnect_user(self, user_id: str):
        """Remove user WebSocket connection"""
        async with self._lock:
            self._user_connections.pop(user_id, None)
        print(f"🔴 User {user_id} disconnected")
    
    async def send_to_user(self, user_id: str, message: dict) -> bool:
        """Send message to specific user"""
        websocket = self._user_connections.get(user_id)
        if websocket:
            try:
                await websocket.send_json(message)
                return True
            except Exception as e:
                print(f"Error sending to user {user_id}: {e}")
                await self.disconnect_user(user_id)
        return False
    
    def is_user_connected(self, user_id: str) -> bool:
        """Check if user is connected"""
        return user_id in self._user_connections
    
    # =========================================================================
    # CS AGENT CONNECTION MANAGEMENT
    # =========================================================================
    
    async def connect_cs(self, websocket: WebSocket, agent_id: str):
        """Accept and store CS agent WebSocket connection"""
        await websocket.accept()
        async with self._lock:
            # Close existing connection if any
            if agent_id in self._cs_connections:
                try:
                    await self._cs_connections[agent_id].close()
                except:
                    pass
            self._cs_connections[agent_id] = websocket
            self._available_cs.add(agent_id)
            
            # Initialize session tracking
            if agent_id not in self._agent_sessions:
                self._agent_sessions[agent_id] = set()
        
        print(f"🟢 CS Agent {agent_id} connected via WebSocket")
    
    async def disconnect_cs(self, agent_id: str):
        """Remove CS agent WebSocket connection"""
        async with self._lock:
            self._cs_connections.pop(agent_id, None)
            self._available_cs.discard(agent_id)
        print(f"🔴 CS Agent {agent_id} disconnected")
    
    async def send_to_cs(self, agent_id: str, message: dict) -> bool:
        """Send message to specific CS agent"""
        websocket = self._cs_connections.get(agent_id)
        if websocket:
            try:
                await websocket.send_json(message)
                return True
            except Exception as e:
                print(f"Error sending to CS {agent_id}: {e}")
                await self.disconnect_cs(agent_id)
        return False
    
    async def broadcast_to_available_cs(self, message: dict):
        """Broadcast message to all available CS agents"""
        for agent_id in list(self._available_cs):
            await self.send_to_cs(agent_id, message)
    
    async def broadcast_to_all_cs(self, message: dict):
        """Broadcast message to all connected CS agents"""
        for agent_id in list(self._cs_connections.keys()):
            await self.send_to_cs(agent_id, message)
    
    def is_cs_connected(self, agent_id: str) -> bool:
        """Check if CS agent is connected"""
        return agent_id in self._cs_connections
    
    # =========================================================================
    # CS AVAILABILITY MANAGEMENT
    # =========================================================================
    
    async def set_agent_available(self, agent_id: str):
        """Set CS agent as available"""
        async with self._lock:
            if agent_id in self._cs_connections:
                self._available_cs.add(agent_id)
    
    async def set_agent_busy(self, agent_id: str):
        """Set CS agent as busy (not accepting new chats)"""
        async with self._lock:
            self._available_cs.discard(agent_id)
    
    def get_available_cs_count(self) -> int:
        """Get count of available CS agents"""
        return len(self._available_cs)
    
    def get_available_cs_list(self) -> list:
        """Get list of available CS agent IDs"""
        return list(self._available_cs)
    
    # =========================================================================
    # SESSION-AGENT MAPPING
    # =========================================================================
    
    async def assign_session_to_agent(self, agent_id: str, session_id: str):
        """Track that an agent is handling a session"""
        async with self._lock:
            if agent_id not in self._agent_sessions:
                self._agent_sessions[agent_id] = set()
            self._agent_sessions[agent_id].add(session_id)
    
    async def remove_session_from_agent(self, agent_id: str, session_id: str):
        """Remove session from agent's tracking"""
        async with self._lock:
            if agent_id in self._agent_sessions:
                self._agent_sessions[agent_id].discard(session_id)
    
    def get_agent_session_count(self, agent_id: str) -> int:
        """Get number of sessions an agent is handling"""
        return len(self._agent_sessions.get(agent_id, set()))
    
    def get_agent_sessions(self, agent_id: str) -> Set[str]:
        """Get all sessions an agent is handling"""
        return self._agent_sessions.get(agent_id, set()).copy()
    
    # =========================================================================
    # STATUS & STATS
    # =========================================================================
    
    def get_status(self) -> dict:
        """Get overall WebSocket status"""
        return {
            "connected_users": len(self._user_connections),
            "connected_cs_agents": len(self._cs_connections),
            "available_cs_agents": len(self._available_cs),
            "user_ids": list(self._user_connections.keys()),
            "cs_agent_ids": list(self._cs_connections.keys()),
            "available_cs_ids": list(self._available_cs),
        }
    
    async def notify_new_escalation(
        self, 
        session_id: str, 
        user_id: str, 
        reason: str,
        last_question: Optional[str] = None
    ):
        """Notify all available CS agents about new escalation"""
        message = {
            "type": "new_escalation",
            "session_id": session_id,
            "user_id": user_id,
            "reason": reason,
            "last_question": last_question,
        }
        await self.broadcast_to_available_cs(message)


# Singleton instance
_ws_manager: Optional[WebSocketManager] = None


def get_ws_manager() -> WebSocketManager:
    """Get singleton WebSocket manager"""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager