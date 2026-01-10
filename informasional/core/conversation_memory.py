# core/conversation_memory.py

"""
Conversation Memory System
Maintains chat history and context for multi-turn conversations
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import threading

class ConversationMessage:
    """Represents a single message in conversation"""
    
    def __init__(self, role: str, content: str, timestamp: Optional[datetime] = None):
        self.role = role  # 'user' or 'assistant'
        self.content = content
        self.timestamp = timestamp or datetime.now()
    
    def to_dict(self) -> dict:
        return {
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ConversationMessage':
        return cls(
            role=data['role'],
            content=data['content'],
            timestamp=datetime.fromisoformat(data['timestamp'])
        )


class ConversationMemory:
    """
    In-memory conversation storage with automatic cleanup
    Stores conversation history per session_id
    """
    
    def __init__(self, max_history: int = 10, ttl_minutes: int = 60):
        """
        Args:
            max_history: Maximum number of messages to keep per session
            ttl_minutes: Time-to-live for sessions in minutes
        """
        self.conversations: Dict[str, List[ConversationMessage]] = defaultdict(list)
        self.last_activity: Dict[str, datetime] = {}
        self.max_history = max_history
        self.ttl = timedelta(minutes=ttl_minutes)
        self.lock = threading.Lock()
        
        # Start cleanup thread
        self._start_cleanup_thread()
    
    def add_message(self, session_id: str, role: str, content: str) -> None:
        """
        Add a message to conversation history
        
        Args:
            session_id: Unique session identifier
            role: 'user' or 'assistant'
            content: Message content
        """
        with self.lock:
            message = ConversationMessage(role, content)
            self.conversations[session_id].append(message)
            self.last_activity[session_id] = datetime.now()
            
            # Trim history if exceeds max_history
            if len(self.conversations[session_id]) > self.max_history:
                self.conversations[session_id] = self.conversations[session_id][-self.max_history:]
    
    def get_history(self, session_id: str, limit: Optional[int] = None) -> List[ConversationMessage]:
        """
        Get conversation history for a session
        
        Args:
            session_id: Unique session identifier
            limit: Maximum number of recent messages to return
        
        Returns:
            List of ConversationMessage objects
        """
        with self.lock:
            messages = self.conversations.get(session_id, [])
            if limit:
                messages = messages[-limit:]
            return messages
    
    def get_formatted_history(self, session_id: str, limit: Optional[int] = None) -> str:
        """
        Get conversation history formatted as string for LLM context
        
        Args:
            session_id: Unique session identifier
            limit: Maximum number of recent messages
        
        Returns:
            Formatted conversation history string
        """
        messages = self.get_history(session_id, limit)
        
        if not messages:
            return "No previous conversation."
        
        formatted = []
        for msg in messages:
            role = "User" if msg.role == "user" else "Assistant"
            formatted.append(f"{role}: {msg.content}")
        
        return "\n\n".join(formatted)
    
    def clear_session(self, session_id: str) -> None:
        """Clear conversation history for a specific session"""
        with self.lock:
            if session_id in self.conversations:
                del self.conversations[session_id]
            if session_id in self.last_activity:
                del self.last_activity[session_id]
    
    def clear_all(self) -> None:
        """Clear all conversation histories"""
        with self.lock:
            self.conversations.clear()
            self.last_activity.clear()
    
    def _cleanup_expired_sessions(self) -> None:
        """Remove sessions that have exceeded TTL"""
        with self.lock:
            now = datetime.now()
            expired_sessions = [
                session_id for session_id, last_time in self.last_activity.items()
                if now - last_time > self.ttl
            ]
            
            for session_id in expired_sessions:
                del self.conversations[session_id]
                del self.last_activity[session_id]
            
            if expired_sessions:
                print(f"[ConversationMemory] Cleaned up {len(expired_sessions)} expired sessions")
    
    def _start_cleanup_thread(self) -> None:
        """Start background thread for periodic cleanup"""
        def cleanup_loop():
            import time
            while True:
                time.sleep(300)  # Run every 5 minutes
                self._cleanup_expired_sessions()
        
        thread = threading.Thread(target=cleanup_loop, daemon=True)
        thread.start()
    
    def get_stats(self) -> dict:
        """Get memory statistics"""
        with self.lock:
            return {
                'total_sessions': len(self.conversations),
                'total_messages': sum(len(msgs) for msgs in self.conversations.values()),
                'max_history_per_session': self.max_history,
                'ttl_minutes': self.ttl.total_seconds() / 60
            }


# Global singleton instance
_conversation_memory = None

def get_conversation_memory() -> ConversationMemory:
    """Get or create global conversation memory instance"""
    global _conversation_memory
    if _conversation_memory is None:
        _conversation_memory = ConversationMemory(
            max_history=10,  # Keep last 10 messages
            ttl_minutes=60   # 1 hour session timeout
        )
    return _conversation_memory


# Utility functions for easy access

def add_user_message(session_id: str, content: str) -> None:
    """Add user message to conversation"""
    memory = get_conversation_memory()
    memory.add_message(session_id, 'user', content)


def add_assistant_message(session_id: str, content: str) -> None:
    """Add assistant message to conversation"""
    memory = get_conversation_memory()
    memory.add_message(session_id, 'assistant', content)


def get_conversation_context(session_id: str, max_turns: int = 5) -> str:
    """
    Get formatted conversation context for RAG
    
    Args:
        session_id: Session identifier
        max_turns: Maximum number of conversation turns to include
    
    Returns:
        Formatted context string
    """
    memory = get_conversation_memory()
    # Get last N*2 messages (N user + N assistant)
    history = memory.get_formatted_history(session_id, limit=max_turns * 2)
    
    if history == "No previous conversation.":
        return ""
    
    return f"""
=== CONVERSATION HISTORY ===
{history}
=== END HISTORY ===

INSTRUCTION: Use the above conversation history for context. If the current question references previous topics, connect them appropriately.
"""


def clear_conversation(session_id: str) -> None:
    """Clear conversation for a session"""
    memory = get_conversation_memory()
    memory.clear_session(session_id)