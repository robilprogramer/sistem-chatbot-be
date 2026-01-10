from typing import Any, Dict
import uuid

from fastapi import APIRouter, HTTPException

from transaksional.app.config import settings
from transaksional.app.form_manager import get_form_manager
from transaksional.app.session_state import get_session_manager

router = APIRouter(
    prefix=f"{settings.transactional_prefix}/session",
    tags=["Session"]
)


@router.post("/new")
async def create_session():
    """Create a new registration session."""
    form_manager = get_form_manager()
    session_manager = get_session_manager()
    
    first_step = form_manager.get_first_step()
    session = session_manager.create_session(initial_step=first_step.id if first_step else "")
    
    welcome = form_manager.get_welcome_message()
    session.add_message("assistant", welcome)
    
    steps = form_manager.get_steps()
    step_info = {
        "current": session.current_step,
        "current_index": 0,
        "total_steps": len(steps),
        "steps": [{"id": s.id, "name": s.name, "icon": s.raw_config.get("icon", "")} for s in steps]
    }
    
    return {
        "session_id": session.session_id,
        "message": welcome,
        "current_step": session.current_step,
        "step_info": step_info
    }


@router.get("/{session_id}")
async def get_session(session_id: str):
    """Get session details by ID."""
    session_manager = get_session_manager()
    form_manager = get_form_manager()
    
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    completion = form_manager.calculate_completion(session.raw_data)
    steps = form_manager.get_steps()
    
    return {
        "session_id": session.session_id,
        "current_step": session.current_step,
        "status": session.status.value,
        "completion_percentage": completion,
        "raw_data": session.raw_data,
        "step_info": {
            "current": session.current_step,
            "total_steps": len(steps),
            "steps": [{"id": s.id, "name": s.name} for s in steps]
        }
    }


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    get_session_manager().delete_session(session_id)
    return {"message": "Session deleted"}