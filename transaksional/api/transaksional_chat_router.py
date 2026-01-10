from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from transaksional.app.config import settings
from transaksional.app.chat_handler import get_chat_handler
from transaksional.app.database import get_db_manager
from transaksional.app.file_storage import get_file_storage, FileValidationError

router = APIRouter(
    prefix=settings.transactional_prefix,
    tags=["Chat"]
)


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    session_id: str
    response: str
    current_step: str
    phase: str
    completion_percentage: float
    can_advance: bool = False
    can_confirm: bool = False
    can_go_back: bool = False
    is_complete: bool = False
    registration_number: Optional[str] = None
    registration_status: Optional[str] = None
    step_info: Optional[Dict[str, Any]] = None
    documents_status: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = {}


@router.post("/chat", response_model=ChatResponse)
async def chat(
    session_id: Optional[str] = Form(None),
    message: str = Form(...),
    file: Optional[UploadFile] = File(None)
):
    """Process chat message with optional file upload."""
    print(f"Received message: {message} | Session ID: {session_id}")
    if not session_id:
        session_id = str(uuid.uuid4())
    
    file_path = None
    file_info = None
    
    if file and file.filename:
        try:
            file_storage = get_file_storage()
            result = await file_storage.save_file(file=file, session_id=session_id, file_type="document")
            file_path = result["file_path"]
            file_info = result
        except FileValidationError as e:
            return ChatResponse(
                session_id=session_id,
                response=f"❌ {e.message}",
                current_step="",
                phase="error",
                completion_percentage=0
            )
        except Exception as e:
            print(f"File upload error: {e}")
    
    try:
        chat_handler = get_chat_handler()
        result = await chat_handler.process_message(session_id, message, file_path, file_info)
        
        try:
            db = get_db_manager()
            db.log_conversation(session_id, "user", message)
            db.log_conversation(session_id, "assistant", result.response)
        except:
            pass
        
        return ChatResponse(
            session_id=result.session_id,
            response=result.response,
            current_step=result.current_step,
            phase=result.phase,
            completion_percentage=result.completion_percentage,
            can_advance=result.can_advance,
            can_confirm=result.can_confirm,
            can_go_back=result.can_go_back,
            is_complete=result.is_complete,
            registration_number=result.registration_number,
            registration_status=result.registration_status,
            step_info=result.step_info,
            documents_status=result.documents_status,
            metadata=result.metadata or {}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/json", response_model=ChatResponse)
async def chat_json(request: ChatRequest):
    """Process chat message via JSON body."""
    session_id = request.session_id or str(uuid.uuid4())
    chat_handler = get_chat_handler()
    result = await chat_handler.process_message(session_id, request.message)
    
    return ChatResponse(
        session_id=result.session_id,
        response=result.response,
        current_step=result.current_step,
        phase=result.phase,
        completion_percentage=result.completion_percentage,
        can_advance=result.can_advance,
        can_confirm=result.can_confirm,
        can_go_back=result.can_go_back,
        is_complete=result.is_complete,
        registration_number=result.registration_number,
        registration_status=result.registration_status,
        step_info=result.step_info,
        documents_status=result.documents_status,
        metadata=result.metadata or {}
    )