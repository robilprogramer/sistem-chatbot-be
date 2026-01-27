"""
CS Package - Customer Service Live Chat Integration

File: cs/__init__.py

Modules:
- schemas: Pydantic models
- escalation: Escalation detection
- session_manager: Session & queue management
- websocket_manager: WebSocket connections
- router: User WebSocket & main CS APIs
- cs_agent_router: CS Agent APIs
"""

from .schemas import (
    ChatMode,
    EscalationReason,
    CSAgentStatus,
    ChatRequestWithSession,
    ChatResponseWithMode,
)

from .escalation import (
    EscalationDetector,
    get_escalation_detector,
)

from .session_manager import (
    ChatSession,
    SessionManager,
    get_session_manager,
)

from .websocket_manager import (
    WebSocketManager,
    get_ws_manager,
)

__all__ = [
    # Schemas
    "ChatMode",
    "EscalationReason", 
    "CSAgentStatus",
    "ChatRequestWithSession",
    "ChatResponseWithMode",
    
    # Escalation
    "EscalationDetector",
    "get_escalation_detector",
    
    # Session
    "ChatSession",
    "SessionManager",
    "get_session_manager",
    
    # WebSocket
    "WebSocketManager",
    "get_ws_manager",
]