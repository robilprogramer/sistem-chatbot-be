"""
CS Schemas - Pydantic models untuk Customer Service

File: transaksional/app/cs/schemas.py
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime
from enum import Enum


# ============================================================================
# ENUMS
# ============================================================================

class ChatMode(str, Enum):
    """Mode chat saat ini"""
    BOT = "bot"              # Chat dengan RAG bot
    PENDING_CS = "pending_cs" # Menunggu CS
    CS = "cs"                # Chat dengan CS agent


class EscalationReason(str, Enum):
    """Alasan eskalasi ke CS"""
    EXPLICIT_REQUEST = "explicit_request"    # User minta bicara CS
    LOW_CONFIDENCE = "low_confidence"        # Bot tidak yakin jawaban
    LOOP_DETECTED = "loop_detected"          # Bot stuck/berulang
    SENTIMENT_NEGATIVE = "sentiment_negative" # User frustasi
    COMPLEX_QUERY = "complex_query"          # Pertanyaan kompleks


class CSAgentStatus(str, Enum):
    """Status CS Agent"""
    ONLINE = "online"    # Siap menerima chat
    BUSY = "busy"        # Tidak menerima chat baru
    OFFLINE = "offline"  # Tidak tersedia


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class ChatRequestWithSession(BaseModel):
    """Request chat dengan session tracking"""
    message: str = Field(..., min_length=1, max_length=2000)
    user_id: str = Field(..., min_length=1, max_length=100)
    session_id: Optional[str] = None
    
    # Registration context (jika dalam proses pendaftaran)
    registration_context: Optional[dict] = None


class CSEscalationRequest(BaseModel):
    """Request untuk eskalasi ke CS"""
    user_id: str
    session_id: str
    reason: EscalationReason
    last_bot_response: Optional[str] = None
    last_user_message: Optional[str] = None


class CSAgentActionRequest(BaseModel):
    """Request action dari CS agent"""
    agent_id: str
    action: str  # accept, close, transfer
    session_id: str
    message: Optional[str] = None


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class ChatResponseWithMode(BaseModel):
    """Response chat dengan info mode"""
    response: str
    mode: ChatMode
    session_id: str
    
    # Escalation info (jika ada)
    should_escalate: bool = False
    escalation_reason: Optional[EscalationReason] = None
    
    # CS info (jika mode == CS)
    cs_agent_id: Optional[str] = None
    cs_agent_name: Optional[str] = None
    queue_position: Optional[int] = None
    estimated_wait_time: Optional[int] = None  # dalam menit
    
    # Metadata
    confidence: Optional[float] = None
    sources: Optional[List[str]] = None


class CSStatusResponse(BaseModel):
    """Response status CS system"""
    available: bool
    available_agents: int
    estimated_wait_time: int  # dalam menit
    queue_length: int


class QueueItemResponse(BaseModel):
    """Item dalam antrian CS"""
    position: int
    session_id: str
    user_id: str
    escalation_reason: Optional[str] = None
    waiting_since: datetime
    estimated_wait_time: int


# ============================================================================
# WEBSOCKET MESSAGE SCHEMAS
# ============================================================================

class WSMessageBase(BaseModel):
    """Base WebSocket message"""
    type: str
    timestamp: datetime = Field(default_factory=datetime.now)


class WSMessageToUser(WSMessageBase):
    """Message dari server ke user"""
    # type: cs_assigned, cs_message, queue_update, session_closed
    content: Optional[str] = None
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    position: Optional[int] = None
    message: Optional[str] = None


class WSMessageToCS(WSMessageBase):
    """Message dari server ke CS agent"""
    # type: new_escalation, user_message, queue_update
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    content: Optional[str] = None
    reason: Optional[str] = None
    queue: Optional[List[dict]] = None


class WSMessageFromUser(BaseModel):
    """Message dari user ke server"""
    type: str  # message
    content: str


class WSMessageFromCS(BaseModel):
    """Message dari CS agent ke server"""
    type: str  # accept_session, message, close_session, set_status
    session_id: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None