"""
Auto-Trigger System - Idle Detection & Auto Messages
=====================================================
Features:
- Detect idle users
- Send automatic follow-up messages
- Trigger rating prompts
- Background scheduler
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
from abc import ABC, abstractmethod


class TriggerType(str, Enum):
    IDLE = "idle"                     # User hasn't messaged in X minutes
    STEP_STUCK = "step_stuck"         # User stuck on same step for X minutes
    INCOMPLETE = "incomplete"          # Form completion below X%
    FOLLOW_UP = "follow_up"           # Post-registration follow-up
    RATING_PROMPT = "rating_prompt"   # Ask for rating
    REMINDER = "reminder"             # General reminder


@dataclass
class TriggerConfig:
    """Configuration for an auto-trigger"""
    id: int
    name: str
    trigger_type: TriggerType
    conditions: Dict[str, Any]
    message_template: str
    priority: int = 0
    max_triggers_per_session: int = 3
    cooldown_minutes: int = 10
    is_active: bool = True
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TriggerConfig":
        return cls(
            id=data.get("id", 0),
            name=data.get("trigger_name", data.get("name", "")),
            trigger_type=TriggerType(data.get("trigger_type", "idle")),
            conditions=data.get("conditions", {}),
            message_template=data.get("message_template", ""),
            priority=data.get("priority", 0),
            max_triggers_per_session=data.get("max_triggers_per_session", 3),
            cooldown_minutes=data.get("cooldown_minutes", 10),
            is_active=data.get("is_active", True)
        )


@dataclass
class SessionActivity:
    """Track session activity for idle detection"""
    session_id: str
    user_id: Optional[str] = None
    last_activity_at: datetime = field(default_factory=datetime.now)
    last_message_at: Optional[datetime] = None
    current_step: Optional[str] = None
    completion_percentage: float = 0
    is_idle: bool = False
    idle_since: Optional[datetime] = None
    total_idle_triggers: int = 0
    
    def update_activity(self, step: str = None, completion: float = None):
        """Update activity timestamp"""
        self.last_activity_at = datetime.now()
        self.last_message_at = datetime.now()
        self.is_idle = False
        self.idle_since = None
        if step:
            self.current_step = step
        if completion is not None:
            self.completion_percentage = completion
    
    def mark_idle(self):
        """Mark session as idle"""
        if not self.is_idle:
            self.is_idle = True
            self.idle_since = datetime.now()
    
    def get_idle_minutes(self) -> float:
        """Get minutes since last activity"""
        if self.last_activity_at:
            return (datetime.now() - self.last_activity_at).total_seconds() / 60
        return 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "current_step": self.current_step,
            "completion_percentage": self.completion_percentage,
            "is_idle": self.is_idle,
            "idle_minutes": self.get_idle_minutes(),
            "total_idle_triggers": self.total_idle_triggers
        }


@dataclass
class TriggerLog:
    """Log of triggered messages"""
    session_id: str
    trigger_id: int
    trigger_name: str
    message_sent: str
    triggered_at: datetime = field(default_factory=datetime.now)
    user_responded: bool = False
    response_at: Optional[datetime] = None


class MessageSender(ABC):
    """Abstract base class for sending messages"""
    
    @abstractmethod
    async def send_message(self, session_id: str, message: str, metadata: Dict = None) -> bool:
        """Send message to user"""
        pass


class WebSocketMessageSender(MessageSender):
    """Send messages via WebSocket"""
    
    def __init__(self, connection_manager=None):
        self.connection_manager = connection_manager
    
    async def send_message(self, session_id: str, message: str, metadata: Dict = None) -> bool:
        if not self.connection_manager:
            return False
        
        try:
            await self.connection_manager.send_message(
                session_id,
                {
                    "type": "auto_message",
                    "message": message,
                    "metadata": metadata or {},
                    "timestamp": datetime.now().isoformat()
                }
            )
            return True
        except Exception as e:
            print(f"Failed to send WebSocket message: {e}")
            return False


class AutoTriggerManager:
    """
    Manages automatic trigger messages for idle detection,
    follow-ups, and rating prompts.
    """
    
    def __init__(self, 
                 db_manager=None,
                 message_sender: MessageSender = None,
                 check_interval_seconds: int = 60,
                 default_idle_minutes: int = 5):
        self._db = db_manager
        self.message_sender = message_sender
        self.check_interval = check_interval_seconds
        self.default_idle_minutes = default_idle_minutes
        
        # In-memory tracking
        self._sessions: Dict[str, SessionActivity] = {}
        self._trigger_logs: Dict[str, List[TriggerLog]] = {}
        self._triggers: List[TriggerConfig] = []
        
        # Background task
        self._running = False
        self._task = None
    
    @property
    def db(self):
        if self._db is None:
            try:
                from transaksional.app.database import get_db_manager
                self._db = get_db_manager()
            except:
                pass
        return self._db
    
    def load_triggers_from_db(self):
        """Load trigger configurations from database"""
        if not self.db:
            return
        
        try:
            triggers = self.db.get_active_triggers()
            self._triggers = [TriggerConfig.from_dict(t) for t in triggers]
        except Exception as e:
            print(f"Error loading triggers: {e}")
    
    def load_triggers_from_config(self, triggers: List[Dict[str, Any]]):
        """Load triggers from config dict"""
        self._triggers = [TriggerConfig.from_dict(t) for t in triggers]
    
    def add_trigger(self, trigger: TriggerConfig):
        """Add a trigger configuration"""
        self._triggers.append(trigger)
    
    def update_session_activity(self, session_id: str, user_id: str = None,
                                 step: str = None, completion: float = None):
        """Update session activity (call this on every user message)"""
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionActivity(
                session_id=session_id,
                user_id=user_id
            )
        
        session = self._sessions[session_id]
        session.update_activity(step, completion)
        
        if user_id:
            session.user_id = user_id
        
        # Save to DB
        if self.db:
            try:
                self.db.update_session_activity(
                    session_id=session_id,
                    user_id=user_id,
                    current_step=step,
                    completion=completion
                )
            except:
                pass
    
    def mark_user_responded(self, session_id: str):
        """Mark that user responded to an auto-message"""
        if session_id in self._trigger_logs:
            for log in reversed(self._trigger_logs[session_id]):
                if not log.user_responded:
                    log.user_responded = True
                    log.response_at = datetime.now()
                    break
    
    def get_session_activity(self, session_id: str) -> Optional[SessionActivity]:
        """Get session activity info"""
        return self._sessions.get(session_id)
    
    def _check_trigger_conditions(self, trigger: TriggerConfig, 
                                   session: SessionActivity) -> bool:
        """Check if trigger conditions are met"""
        conditions = trigger.conditions
        
        if trigger.trigger_type == TriggerType.IDLE:
            idle_minutes = conditions.get("idle_minutes", self.default_idle_minutes)
            return session.get_idle_minutes() >= idle_minutes
        
        elif trigger.trigger_type == TriggerType.STEP_STUCK:
            required_step = conditions.get("step")
            if required_step and session.current_step != required_step:
                return False
            stuck_minutes = conditions.get("stuck_minutes", 10)
            return session.get_idle_minutes() >= stuck_minutes
        
        elif trigger.trigger_type == TriggerType.INCOMPLETE:
            min_completion = conditions.get("completion_below", 50)
            min_idle = conditions.get("idle_minutes", 5)
            return (session.completion_percentage < min_completion and 
                    session.get_idle_minutes() >= min_idle)
        
        elif trigger.trigger_type == TriggerType.RATING_PROMPT:
            # Rating prompt after completion
            if conditions.get("after_completion"):
                return session.completion_percentage >= 100
            return False
        
        return False
    
    def _check_cooldown(self, trigger: TriggerConfig, session_id: str) -> bool:
        """Check if trigger is still in cooldown period"""
        if session_id not in self._trigger_logs:
            return False
        
        cooldown_threshold = datetime.now() - timedelta(minutes=trigger.cooldown_minutes)
        
        for log in self._trigger_logs[session_id]:
            if log.trigger_id == trigger.id and log.triggered_at > cooldown_threshold:
                return True
        
        return False
    
    def _get_trigger_count(self, trigger: TriggerConfig, session_id: str) -> int:
        """Get number of times trigger has fired for session"""
        if session_id not in self._trigger_logs:
            return 0
        
        return sum(1 for log in self._trigger_logs[session_id] 
                   if log.trigger_id == trigger.id)
    
    def _format_message(self, template: str, session: SessionActivity) -> str:
        """Format message template with session data"""
        return template.format(
            session_id=session.session_id,
            user_id=session.user_id or "User",
            current_step=session.current_step or "langkah saat ini",
            completion=f"{session.completion_percentage:.0f}",
            idle_minutes=f"{session.get_idle_minutes():.0f}"
        )
    
    async def check_and_trigger(self, session_id: str) -> Optional[str]:
        """
        Check triggers for a session and send message if conditions met.
        Returns the message sent, or None.
        """
        session = self._sessions.get(session_id)
        if not session:
            return None
        
        # Mark as idle if needed
        if session.get_idle_minutes() >= self.default_idle_minutes:
            session.mark_idle()
        
        # Sort triggers by priority (highest first)
        sorted_triggers = sorted(self._triggers, key=lambda t: t.priority, reverse=True)
        
        for trigger in sorted_triggers:
            if not trigger.is_active:
                continue
            
            # Check max triggers
            if self._get_trigger_count(trigger, session_id) >= trigger.max_triggers_per_session:
                continue
            
            # Check cooldown
            if self._check_cooldown(trigger, session_id):
                continue
            
            # Check conditions
            if not self._check_trigger_conditions(trigger, session):
                continue
            
            # Trigger matched! Format and send message
            message = self._format_message(trigger.message_template, session)
            
            # Log the trigger
            log = TriggerLog(
                session_id=session_id,
                trigger_id=trigger.id,
                trigger_name=trigger.name,
                message_sent=message
            )
            
            if session_id not in self._trigger_logs:
                self._trigger_logs[session_id] = []
            self._trigger_logs[session_id].append(log)
            
            session.total_idle_triggers += 1
            
            # Save to DB
            if self.db:
                try:
                    self.db.log_trigger(
                        session_id=session_id,
                        trigger_id=trigger.id,
                        trigger_name=trigger.name,
                        message_sent=message
                    )
                except:
                    pass
            
            # Send message
            if self.message_sender:
                await self.message_sender.send_message(
                    session_id, 
                    message,
                    {"trigger_type": trigger.trigger_type.value, "trigger_name": trigger.name}
                )
            
            return message
        
        return None
    
    async def check_all_sessions(self) -> Dict[str, str]:
        """Check all active sessions and trigger messages"""
        triggered = {}
        
        for session_id in list(self._sessions.keys()):
            message = await self.check_and_trigger(session_id)
            if message:
                triggered[session_id] = message
        
        return triggered
    
    async def _background_checker(self):
        """Background task to check sessions periodically"""
        while self._running:
            try:
                triggered = await self.check_all_sessions()
                if triggered:
                    print(f"Auto-triggered {len(triggered)} messages")
            except Exception as e:
                print(f"Error in background checker: {e}")
            
            await asyncio.sleep(self.check_interval)
    
    def start_background_checker(self):
        """Start the background checking task"""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._background_checker())
        print(f"Started auto-trigger background checker (interval: {self.check_interval}s)")
    
    def stop_background_checker(self):
        """Stop the background checking task"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        print("Stopped auto-trigger background checker")
    
    def cleanup_session(self, session_id: str):
        """Clean up session data"""
        if session_id in self._sessions:
            del self._sessions[session_id]
        if session_id in self._trigger_logs:
            del self._trigger_logs[session_id]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get trigger statistics"""
        total_sessions = len(self._sessions)
        idle_sessions = sum(1 for s in self._sessions.values() if s.is_idle)
        total_triggers = sum(len(logs) for logs in self._trigger_logs.values())
        
        return {
            "active_sessions": total_sessions,
            "idle_sessions": idle_sessions,
            "total_triggers_sent": total_triggers,
            "triggers_configured": len(self._triggers),
            "check_interval_seconds": self.check_interval,
            "is_running": self._running
        }


# =============================================================================
# DEFAULT TRIGGER CONFIGURATIONS
# =============================================================================

DEFAULT_TRIGGERS = [
    {
        "id": 1,
        "name": "idle_reminder",
        "trigger_type": "idle",
        "conditions": {"idle_minutes": 5},
        "message_template": "Hai! Sepertinya kamu sedang sibuk. Jangan lupa lanjutkan pendaftaran ya! 😊\n\nKamu sudah mengisi {completion}% data.",
        "priority": 10,
        "max_triggers_per_session": 2,
        "cooldown_minutes": 10
    },
    {
        "id": 2,
        "name": "document_stuck",
        "trigger_type": "step_stuck",
        "conditions": {"step": "documents", "stuck_minutes": 10},
        "message_template": "Butuh bantuan upload dokumen? 📄\n\nKamu bisa upload beberapa file sekaligus lho! Cukup pilih beberapa file dan kirim.",
        "priority": 8,
        "max_triggers_per_session": 1,
        "cooldown_minutes": 15
    },
    {
        "id": 3,
        "name": "incomplete_reminder",
        "trigger_type": "incomplete",
        "conditions": {"completion_below": 50, "idle_minutes": 15},
        "message_template": "Data pendaftaran kamu baru {completion}% lengkap.\n\nYuk selesaikan! Ketik 'lanjut' untuk melanjutkan. 💪",
        "priority": 5,
        "max_triggers_per_session": 1,
        "cooldown_minutes": 30
    },
    {
        "id": 4,
        "name": "rating_after_complete",
        "trigger_type": "rating_prompt",
        "conditions": {"after_completion": True},
        "message_template": "Terima kasih telah menyelesaikan pendaftaran! 🎉\n\nBoleh minta waktu sebentar untuk memberikan rating pengalaman kamu?\n\n⭐ Ketik angka 1-5 (5 = sangat puas)",
        "priority": 15,
        "max_triggers_per_session": 1,
        "cooldown_minutes": 60
    }
]


# =============================================================================
# SINGLETON
# =============================================================================

_trigger_manager: Optional[AutoTriggerManager] = None

def get_trigger_manager() -> AutoTriggerManager:
    global _trigger_manager
    if _trigger_manager is None:
        _trigger_manager = AutoTriggerManager()
        _trigger_manager.load_triggers_from_config(DEFAULT_TRIGGERS)
    return _trigger_manager


def init_trigger_manager(db_manager=None, message_sender=None) -> AutoTriggerManager:
    """Initialize trigger manager with dependencies"""
    global _trigger_manager
    _trigger_manager = AutoTriggerManager(
        db_manager=db_manager,
        message_sender=message_sender
    )
    
    # Try loading from DB first, fallback to defaults
    try:
        _trigger_manager.load_triggers_from_db()
        if not _trigger_manager._triggers:
            _trigger_manager.load_triggers_from_config(DEFAULT_TRIGGERS)
    except:
        _trigger_manager.load_triggers_from_config(DEFAULT_TRIGGERS)
    
    return _trigger_manager