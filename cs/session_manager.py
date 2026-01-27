"""
Session Manager - Manage chat sessions dan queue CS

File: transaksional/app/cs/session_manager.py
"""

from typing import Optional, Dict, List
from datetime import datetime
from dataclasses import dataclass, field
import asyncio

from .schemas import ChatMode, EscalationReason


@dataclass
class ChatSession:
    """
    Represents a chat session
    
    Tracks:
    - User info
    - Current mode (bot/pending_cs/cs)
    - CS agent assignment
    - Queue position
    """
    session_id: str
    user_id: str
    mode: ChatMode = ChatMode.BOT
    
    # CS related
    cs_agent_id: Optional[str] = None
    cs_agent_name: Optional[str] = None
    escalation_reason: Optional[EscalationReason] = None
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    escalated_at: Optional[datetime] = None
    cs_connected_at: Optional[datetime] = None
    
    # Queue
    queue_position: Optional[int] = None
    
    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "mode": self.mode.value,
            "cs_agent_id": self.cs_agent_id,
            "cs_agent_name": self.cs_agent_name,
            "escalation_reason": self.escalation_reason.value if self.escalation_reason else None,
            "created_at": self.created_at.isoformat(),
            "escalated_at": self.escalated_at.isoformat() if self.escalated_at else None,
            "cs_connected_at": self.cs_connected_at.isoformat() if self.cs_connected_at else None,
            "queue_position": self.queue_position,
        }


class SessionManager:
    """
    Manages all chat sessions
    
    Responsibilities:
    - Create/get/update sessions
    - Manage CS queue
    - Track mode transitions
    """
    
    def __init__(self):
        # Active sessions: session_id -> ChatSession
        self._sessions: Dict[str, ChatSession] = {}
        
        # User to session mapping: user_id -> session_id
        self._user_sessions: Dict[str, str] = {}
        
        # CS Queue: List of session_ids waiting for CS
        self._queue: List[str] = []
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
    
    async def get_or_create_session(self, user_id: str, session_id: Optional[str] = None) -> ChatSession:
        """Get existing session or create new one"""
        async with self._lock:
            # Check if user has existing session
            if user_id in self._user_sessions:
                existing_session_id = self._user_sessions[user_id]
                if existing_session_id in self._sessions:
                    return self._sessions[existing_session_id]
            
            # Create new session
            new_session_id = session_id or f"session-{user_id}-{datetime.now().timestamp()}"
            session = ChatSession(
                session_id=new_session_id,
                user_id=user_id
            )
            
            self._sessions[new_session_id] = session
            self._user_sessions[user_id] = new_session_id
            
            return session
    
    async def get_session(self, user_id: str) -> Optional[ChatSession]:
        """Get session by user_id"""
        session_id = self._user_sessions.get(user_id)
        if session_id:
            return self._sessions.get(session_id)
        return None
    
    async def get_session_by_id(self, session_id: str) -> Optional[ChatSession]:
        """Get session by session_id"""
        return self._sessions.get(session_id)
    
    async def escalate_to_cs(
        self, 
        user_id: str, 
        reason: EscalationReason
    ) -> Optional[ChatSession]:
        """
        Escalate session to CS queue
        
        Changes mode to PENDING_CS and adds to queue
        """
        async with self._lock:
            session = await self.get_session(user_id)
            if not session:
                return None
            
            # Update session
            session.mode = ChatMode.PENDING_CS
            session.escalation_reason = reason
            session.escalated_at = datetime.now()
            
            # Add to queue if not already
            if session.session_id not in self._queue:
                self._queue.append(session.session_id)
                session.queue_position = len(self._queue)
            
            return session
    
    async def assign_cs_to_session(
        self, 
        session_id: str, 
        agent_id: str,
        agent_name: str = "CS Agent"
    ) -> Optional[ChatSession]:
        """
        Assign CS agent to session
        
        Changes mode to CS and removes from queue
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            
            # Update session
            session.mode = ChatMode.CS
            session.cs_agent_id = agent_id
            session.cs_agent_name = agent_name
            session.cs_connected_at = datetime.now()
            session.queue_position = None
            
            # Remove from queue
            if session_id in self._queue:
                self._queue.remove(session_id)
                # Update queue positions
                await self._update_queue_positions()
            
            return session
    
    async def close_cs_session(self, session_id: str) -> Optional[ChatSession]:
        """
        Close CS session and return to bot mode
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            
            # Reset to bot mode
            session.mode = ChatMode.BOT
            session.cs_agent_id = None
            session.cs_agent_name = None
            session.queue_position = None
            
            # Remove from queue if still there
            if session_id in self._queue:
                self._queue.remove(session_id)
                await self._update_queue_positions()
            
            return session
    
    async def cancel_cs_request(self, user_id: str) -> Optional[ChatSession]:
        """
        Cancel CS request and return to bot mode
        """
        session = await self.get_session(user_id)
        if session:
            return await self.close_cs_session(session.session_id)
        return None
    
    async def get_queue(self) -> List[dict]:
        """Get current CS queue with details"""
        queue_items = []
        
        for position, session_id in enumerate(self._queue, 1):
            session = self._sessions.get(session_id)
            if session:
                queue_items.append({
                    "position": position,
                    "session_id": session_id,
                    "user_id": session.user_id,
                    "escalation_reason": session.escalation_reason.value if session.escalation_reason else None,
                    "waiting_since": session.escalated_at.isoformat() if session.escalated_at else None,
                })
        
        return queue_items
    
    async def get_queue_position(self, session_id: str) -> Optional[int]:
        """Get queue position for session"""
        try:
            return self._queue.index(session_id) + 1
        except ValueError:
            return None
    
    async def get_pending_sessions(self) -> List[ChatSession]:
        """Get all sessions in pending_cs mode"""
        return [
            s for s in self._sessions.values() 
            if s.mode == ChatMode.PENDING_CS
        ]
    
    async def get_active_cs_sessions(self, agent_id: str) -> List[ChatSession]:
        """Get all active CS sessions for an agent"""
        return [
            s for s in self._sessions.values()
            if s.mode == ChatMode.CS and s.cs_agent_id == agent_id
        ]
    
    async def _update_queue_positions(self):
        """Update queue positions after changes"""
        for position, session_id in enumerate(self._queue, 1):
            if session_id in self._sessions:
                self._sessions[session_id].queue_position = position
    
    async def remove_session(self, user_id: str):
        """Remove session completely"""
        async with self._lock:
            session_id = self._user_sessions.pop(user_id, None)
            if session_id:
                self._sessions.pop(session_id, None)
                if session_id in self._queue:
                    self._queue.remove(session_id)
                    await self._update_queue_positions()


# Singleton instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get singleton session manager"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager