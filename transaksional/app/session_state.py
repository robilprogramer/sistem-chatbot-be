"""
Session State - With Database Persistence
==========================================
- Auto-save draft to database
- Recover from disconnect
- Track edit history
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from enum import Enum
import uuid
import json


class SessionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"
    ABANDONED = "abandoned"


@dataclass
class SessionState:
    session_id: str
    current_step: str
    status: SessionStatus = SessionStatus.ACTIVE
    raw_data: Dict[str, Any] = field(default_factory=dict)
    validation_errors: Dict[str, str] = field(default_factory=dict)
    conversation_history: List[Dict] = field(default_factory=list)
    edit_history: List[Dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = None
    registration_number: Optional[str] = None
    
    # Document tracking
    documents_uploaded: Dict[str, Dict] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.expires_at is None:
            self.expires_at = datetime.now() + timedelta(hours=24)
    
    def get_field(self, field_id: str, default: Any = None) -> Any:
        return self.raw_data.get(field_id, default)
    
    def set_field(self, field_id: str, value: Any, field_label: str = None) -> str:
        """Set field and return action type ('create' or 'update')"""
        old_value = self.raw_data.get(field_id)
        action = "update" if old_value is not None else "create"
        
        # Log edit
        if old_value is not None and old_value != value:
            self.edit_history.append({
                "field_id": field_id,
                "field_label": field_label or field_id,
                "old_value": old_value,
                "new_value": value,
                "timestamp": datetime.now().isoformat()
            })
        
        self.raw_data[field_id] = value
        self.updated_at = datetime.now()
        return action
    
    def set_document(self, field_id: str, doc_info: Dict):
        """Track uploaded document"""
        self.documents_uploaded[field_id] = {
            **doc_info,
            "uploaded_at": datetime.now().isoformat()
        }
        self.raw_data[field_id] = doc_info.get("file_path")
        self.updated_at = datetime.now()
    
    def get_document(self, field_id: str) -> Optional[Dict]:
        """Get document info"""
        return self.documents_uploaded.get(field_id)
    
    def delete_field(self, field_id: str):
        if field_id in self.raw_data:
            del self.raw_data[field_id]
            self.updated_at = datetime.now()
    
    def set_validation_error(self, field_id: str, error: str):
        self.validation_errors[field_id] = error
    
    def clear_validation_error(self, field_id: str):
        if field_id in self.validation_errors:
            del self.validation_errors[field_id]
    
    def add_message(self, role: str, content: str, metadata: Dict = None):
        self.conversation_history.append({
            "role": role,
            "content": content,
            "metadata": metadata,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_recent_messages(self, count: int = 10) -> List[Dict]:
        return self.conversation_history[-count:]
    
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at
    
    def extend_expiry(self, hours: int = 24):
        self.expires_at = datetime.now() + timedelta(hours=hours)
    
    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "current_step": self.current_step,
            "status": self.status.value,
            "raw_data": self.raw_data,
            "validation_errors": self.validation_errors,
            "documents_uploaded": self.documents_uploaded,
            "conversation_history": self.conversation_history,
            "edit_history": self.edit_history,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "registration_number": self.registration_number
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SessionState":
        session = cls(
            session_id=data["session_id"],
            current_step=data["current_step"],
            status=SessionStatus(data.get("status", "active")),
            raw_data=data.get("raw_data", {}),
            validation_errors=data.get("validation_errors", {}),
            conversation_history=data.get("conversation_history", []),
            edit_history=data.get("edit_history", []),
            registration_number=data.get("registration_number")
        )
        session.documents_uploaded = data.get("documents_uploaded", {})
        
        if data.get("created_at"):
            session.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("updated_at"):
            session.updated_at = datetime.fromisoformat(data["updated_at"])
        if data.get("expires_at"):
            session.expires_at = datetime.fromisoformat(data["expires_at"])
        
        return session


class SessionManager:
    def __init__(self, use_db: bool = True):
        self._sessions: Dict[str, SessionState] = {}
        self.use_db = use_db
        self._db = None
    
    @property
    def db(self):
        if self._db is None and self.use_db:
            from  transaksional.app.database import get_db_manager
            self._db = get_db_manager()
        return self._db
    
    def create_session(self, initial_step: str = "") -> SessionState:
        session_id = str(uuid.uuid4())
        session = SessionState(
            session_id=session_id,
            current_step=initial_step
        )
        self._sessions[session_id] = session
        return session
    
    def get_session(self, session_id: str) -> Optional[SessionState]:
        # Check memory first
        session = self._sessions.get(session_id)
        
        if session:
            if session.is_expired():
                self.delete_session(session_id)
                return None
            return session
        
        # Try to recover from database
        if self.use_db and self.db:
            draft = self.db.get_draft(session_id)
            if draft:
                session = SessionState(
                    session_id=session_id,
                    current_step=draft["current_step"],
                    raw_data=draft["raw_data"]
                )
                self._sessions[session_id] = session
                return session
        
        return None
    
    def save_session(self, session: SessionState):
        """Save session to memory and optionally to database"""
        self._sessions[session.session_id] = session
        
        # Auto-save draft to database
        if self.use_db and self.db and session.status == SessionStatus.ACTIVE:
            from  transaksional.app.form_manager import get_form_manager
            form_manager = get_form_manager()
            completion = form_manager.calculate_completion(session.raw_data)
            
            self.db.save_draft(
                session_id=session.session_id,
                current_step=session.current_step,
                raw_data=session.raw_data,
                completion_percentage=completion
            )
    
    def delete_session(self, session_id: str):
        if session_id in self._sessions:
            del self._sessions[session_id]
    
    def cleanup_expired(self) -> int:
        expired = [sid for sid, s in self._sessions.items() if s.is_expired()]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)
    
    def get_active_sessions_count(self) -> int:
        self.cleanup_expired()
        return len(self._sessions)


# Singleton
_session_manager: Optional[SessionManager] = None

def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(use_db=True)
    return _session_manager
