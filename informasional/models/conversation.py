# transaksional/models/conversation.py
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from informasional.utils.db import Base


class Conversation(Base):
    """Model untuk log percakapan chatbot"""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    
    user_message = Column(Text, nullable=True)
    bot_response = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Conversation session={self.session_id}>"


class ConversationState(Base):
    """Model untuk state/context percakapan"""
    __tablename__ = "conversation_state"

    session_id = Column(String(100), primary_key=True)
    
    current_step = Column(String(50), nullable=True)
    collected_data = Column(JSONB, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<ConversationState session={self.session_id} step={self.current_step}>"