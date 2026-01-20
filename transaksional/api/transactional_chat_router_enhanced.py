
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel

from transaksional.app.config import settings
from transaksional.app.chat_handler import get_chat_handler
from transaksional.app.database import get_db_manager
from transaksional.app.file_storage_enhanced import (
    get_file_storage, 
    FileValidationError,
    BatchUploadResult,
    UploadStatus
)
from transaksional.app.auto_trigger import get_trigger_manager
from transaksional.app.rating_system import get_rating_manager, RatingPromptType


router = APIRouter(
    prefix=settings.transactional_prefix,
    tags=["Chat"]
)


# =============================================================================
# MODELS
# =============================================================================

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str


class FileUploadInfo(BaseModel):
    success: bool
    file_name: Optional[str] = None
    original_name: Optional[str] = None
    file_size: int = 0
    error: Optional[str] = None


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
    # Multiple upload info
    upload_batch_id: Optional[str] = None
    upload_results: Optional[List[FileUploadInfo]] = None


class MultipleUploadResponse(BaseModel):
    session_id: str
    batch_id: str
    status: str
    total_files: int
    successful_files: int
    failed_files: int
    results: List[Dict[str, Any]]
    errors: List[str]
    message: str


class RatingRequest(BaseModel):
    session_id: str
    rating: int
    feedback: Optional[str] = None
    user_id: Optional[str] = None
    registration_number: Optional[str] = None


class RatingResponse(BaseModel):
    success: bool
    message: str
    rating_id: Optional[int] = None


# =============================================================================
# CHAT ENDPOINTS
# =============================================================================

@router.post("/chat", response_model=ChatResponse)
async def chat(
    session_id: Optional[str] = Form(None),
    message: str = Form(...),
    files: List[UploadFile] = File(default=[]),  # Multiple files support
    file: Optional[UploadFile] = File(None),      # Single file backward compatibility
    file_type: Optional[str] = Form(None),        # Document type untuk upload
    user_id: str = Form(...)
):
    """
    Process chat message with optional file upload (single or multiple).
    
    - **session_id**: Session ID (auto-generated jika kosong)
    - **message**: Chat message
    - **files**: Multiple files upload (List)
    - **file**: Single file upload (backward compatibility)
    - **file_type**: Tipe dokumen (e.g., "rapor_terakhir", "akta_kelahiran")
    - **user_id**: User ID
    """

    if not session_id:
        session_id = str(uuid.uuid4())
    
    # Update session activity for idle detection
    trigger_manager = get_trigger_manager()
    trigger_manager.update_session_activity(session_id, user_id)
    
    # Check if in rating flow
    rating_manager = get_rating_manager()
    if rating_manager.is_rating_in_progress(session_id):
        rating_result = rating_manager.process_rating_input(session_id, message)
        print(f"Rating input processed: {rating_result}")
        if rating_result.get("is_rating_input"):
            return ChatResponse(
                session_id=session_id,
                response=rating_result.get("response", ""),
                current_step="rating",
                phase="rating",
                completion_percentage=100,
                is_complete=rating_result.get("completed", False),
                metadata={"rating": rating_result.get("rating")}
            )
    
    file_path = None
    file_info = None
    batch_id = None
    upload_results = []
    
    # Combine files from both parameters
    all_files = []
    
    # Add files from 'files' parameter (multiple)
    if files:
        all_files.extend([f for f in files if f and f.filename])
    
    # Add file from 'file' parameter (single, backward compatibility)
    if file and file.filename:
        all_files.append(file)
    
    # Process files
    if all_files:
        file_storage = get_file_storage()
        doc_type = file_type or "document"
        
        if len(all_files) == 1:
            # Single file upload
            try:
                result = await file_storage.save_single_file(
                    file=all_files[0], 
                    session_id=session_id, 
                    file_type=doc_type
                )
                
                if result.success:
                    file_path = result.file_path
                    file_info = {
                        "file_path": result.file_path,
                        "file_name": result.file_name,
                        "original_name": result.original_name,
                        "file_size": result.file_size,
                        "file_type": doc_type
                    }
                    upload_results.append(FileUploadInfo(
                        success=True,
                        file_name=result.file_name,
                        original_name=result.original_name,
                        file_size=result.file_size
                    ))
                else:
                    upload_results.append(FileUploadInfo(
                        success=False,
                        original_name=result.original_name,
                        error=result.error
                    ))
                    return ChatResponse(
                        session_id=session_id,
                        response=f"❌ {result.error}",
                        current_step="",
                        phase="error",
                        completion_percentage=0,
                        upload_results=[r.dict() for r in upload_results]
                    )
                    
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
        
        else:
            # Multiple files upload
            try:
                batch_result: BatchUploadResult = await file_storage.save_multiple_files(
                    files=all_files,
                    session_id=session_id,
                    file_type=doc_type
                )
                
                batch_id = batch_result.batch_id
                
                # Convert results
                for r in batch_result.results:
                    upload_results.append(FileUploadInfo(
                        success=r.success,
                        file_name=r.file_name,
                        original_name=r.original_name,
                        file_size=r.file_size,
                        error=r.error
                    ))
                
                # Get first successful file for chat handler
                successful = [r for r in batch_result.results if r.success]
                if successful:
                    file_path = successful[0].file_path
                    file_info = {
                        "file_path": successful[0].file_path,
                        "file_name": successful[0].file_name,
                        "original_name": successful[0].original_name,
                        "file_size": successful[0].file_size,
                        "file_type": doc_type,
                        "batch_id": batch_id,
                        "total_files": batch_result.total_files,
                        "successful_files": batch_result.successful_files,
                        "failed_files": batch_result.failed_files,
                        "all_files": [
                            {
                                "file_path": r.file_path,
                                "file_name": r.file_name,
                                "original_name": r.original_name,
                                "file_size": r.file_size
                            }
                            for r in batch_result.results if r.success
                        ]
                    }
                
                # Handle batch result status
                if batch_result.status == UploadStatus.FAILED:
                    error_msg = ", ".join(batch_result.errors) if batch_result.errors else "Upload gagal"
                    return ChatResponse(
                        session_id=session_id,
                        response=f"❌ Gagal upload file: {error_msg}",
                        current_step="",
                        phase="error",
                        completion_percentage=0,
                        upload_batch_id=batch_id,
                        upload_results=[r.dict() for r in upload_results]
                    )
                
            except Exception as e:
                print(f"Multiple file upload error: {e}")
                import traceback
                traceback.print_exc()
    
    try:
        chat_handler = get_chat_handler()
        result = await chat_handler.process_message(
            session_id, message, file_path, file_info, user_id
        )
        
        # Update activity with new step and completion
        trigger_manager.update_session_activity(
            session_id, user_id,
            step=result.current_step,
            completion=result.completion_percentage
        )
        
        # Log conversation
        try:
            db = get_db_manager()
            db.log_conversation(session_id, "user", message)
            db.log_conversation(session_id, "assistant", result.response)
        except:
            pass
        
        # Build response message
        response_text = result.response
        
        # Add upload summary if multiple files were uploaded
        if batch_id and upload_results:
            success_count = sum(1 for r in upload_results if r.success)
            fail_count = len(upload_results) - success_count
            
            if success_count > 0:
                upload_summary = f"\n\n📎 **Upload:** {success_count} file berhasil"
                if fail_count > 0:
                    upload_summary += f", {fail_count} file gagal"
                    failed_files = [r.original_name for r in upload_results if not r.success]
                    if failed_files:
                        upload_summary += f"\n❌ Gagal: {', '.join(failed_files[:3])}"
                        if len(failed_files) > 3:
                            upload_summary += f" dan {len(failed_files) - 3} lainnya"
                
                response_text += upload_summary
        
        # Check if registration complete - trigger rating
        if result.is_complete and result.registration_number:
            rating_prompt = rating_manager.start_rating_flow(
                session_id=session_id,
                prompt_type=RatingPromptType.POST_REGISTRATION,
                user_id=user_id,
                registration_number=result.registration_number
            )
            if rating_prompt:
                response_text += f"\n\n---\n\n{rating_prompt}"
        
        return ChatResponse(
            session_id=result.session_id,
            response=response_text,
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
            metadata=result.metadata or {},
            upload_batch_id=batch_id,
            upload_results=[r.dict() for r in upload_results] if upload_results else None
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/json", response_model=ChatResponse)
async def chat_json(request: ChatRequest):
    """Process chat message via JSON body (no file upload)."""
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


# =============================================================================
# DEDICATED MULTIPLE FILE UPLOAD ENDPOINT (Alternative)
# =============================================================================

@router.post("/upload/multiple", response_model=MultipleUploadResponse)
async def upload_multiple_files(
    session_id: str = Form(...),
    file_type: str = Form(...),
    files: List[UploadFile] = File(...),
    user_id: Optional[str] = Form(None),
    registration_number: Optional[str] = Form(None)
):
    """
    Dedicated endpoint untuk upload multiple files.
    Gunakan ini jika ingin upload terpisah dari chat.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
    try:
        file_storage = get_file_storage()
        result: BatchUploadResult = await file_storage.save_multiple_files(
            files=files,
            session_id=session_id,
            file_type=file_type,
            registration_number=registration_number
        )
        
        if result.status == UploadStatus.COMPLETED:
            message = f"✅ Berhasil upload {result.successful_files} file"
        elif result.status == UploadStatus.PARTIAL:
            message = f"⚠️ {result.successful_files} file berhasil, {result.failed_files} file gagal"
        else:
            message = f"❌ Gagal upload file: {', '.join(result.errors)}"
        
        return MultipleUploadResponse(
            session_id=session_id,
            batch_id=result.batch_id,
            status=result.status.value,
            total_files=result.total_files,
            successful_files=result.successful_files,
            failed_files=result.failed_files,
            results=[
                {
                    "success": r.success,
                    "file_name": r.file_name,
                    "original_name": r.original_name,
                    "file_size": r.file_size,
                    "error": r.error
                }
                for r in result.results
            ],
            errors=result.errors,
            message=message
        )
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/upload/batch/{batch_id}")
async def get_batch_info(batch_id: str):
    """Get information about an upload batch."""
    file_storage = get_file_storage()
    files = file_storage.get_batch_files(batch_id)
    
    if not files:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    return {
        "batch_id": batch_id,
        "files": files,
        "total_files": len(files)
    }


@router.delete("/upload/batch/{batch_id}")
async def delete_batch(batch_id: str):
    """Delete an upload batch and all its files."""
    file_storage = get_file_storage()
    success = file_storage.delete_batch(batch_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    return {"success": True, "message": "Batch deleted successfully"}


# =============================================================================
# RATING ENDPOINTS
# =============================================================================

@router.post("/rating", response_model=RatingResponse)
async def submit_rating(request: RatingRequest):
    """Submit a rating directly."""
    rating_manager = get_rating_manager()
    
    try:
        rating = rating_manager.submit_rating(
            session_id=request.session_id,
            rating=request.rating,
            feedback=request.feedback,
            user_id=request.user_id,
            registration_number=request.registration_number
        )
        
        return RatingResponse(
            success=True,
            message="Terima kasih atas rating-nya!",
            rating_id=rating.id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rating/stats")
async def get_rating_stats():
    """Get rating statistics."""
    rating_manager = get_rating_manager()
    stats = rating_manager.get_rating_stats()
    
    return {
        "stats": stats,
        "summary": rating_manager.format_rating_summary(stats)
    }


@router.get("/rating/recent")
async def get_recent_ratings(limit: int = Query(10, ge=1, le=100)):
    """Get recent ratings."""
    rating_manager = get_rating_manager()
    ratings = rating_manager.get_recent_ratings(limit)
    
    return {
        "ratings": [r.to_dict() for r in ratings],
        "count": len(ratings)
    }


# =============================================================================
# SESSION ACTIVITY ENDPOINTS
# =============================================================================

@router.get("/session/{session_id}/activity")
async def get_session_activity(session_id: str):
    """Get session activity info."""
    trigger_manager = get_trigger_manager()
    activity = trigger_manager.get_session_activity(session_id)
    
    if not activity:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return activity.to_dict()


@router.get("/session/{session_id}/files")
async def get_session_files(session_id: str, field_name: Optional[str] = None):
    """Get uploaded files for a session."""
    file_storage = get_file_storage()
    files = file_storage.get_session_files(session_id, field_name)
    
    return {
        "session_id": session_id,
        "files": files,
        "total_files": len(files)
    }


@router.get("/triggers/stats")
async def get_trigger_stats():
    """Get auto-trigger statistics."""
    trigger_manager = get_trigger_manager()
    return trigger_manager.get_stats()


# =============================================================================
# CONFIG ENDPOINTS
# =============================================================================

@router.get("/config/source")
async def get_config_source():
    """Get current config source (yaml/database)."""
    from transaksional.app.config_loader import get_config_loader
    loader = get_config_loader()
    return {
        "source": loader.source.value,
        "fallback": loader.fallback.value
    }


@router.post("/config/switch")
async def switch_config_source(source: str = Form(...)):
    """Switch config source at runtime."""
    if source not in ["yaml", "database"]:
        raise HTTPException(status_code=400, detail="Invalid source. Use 'yaml' or 'database'")
    
    from transaksional.app.config_loader import get_config_loader, ConfigSource
    loader = get_config_loader()
    loader.switch_source(ConfigSource(source))
    
    return {
        "success": True,
        "message": f"Switched to {source}",
        "source": loader.source.value
    }


@router.post("/config/sync/yaml-to-db")
async def sync_yaml_to_db():
    """Sync YAML config to database."""
    from transaksional.app.config_loader import get_config_loader
    loader = get_config_loader()
    success = loader.sync_yaml_to_db()
    
    return {
        "success": success,
        "message": "YAML synced to database" if success else "Sync failed"
    }


@router.post("/config/sync/db-to-yaml")
async def sync_db_to_yaml():
    """Sync database config to YAML."""
    from transaksional.app.config_loader import get_config_loader
    loader = get_config_loader()
    success = loader.sync_db_to_yaml()
    
    return {
        "success": success,
        "message": "Database synced to YAML" if success else "Sync failed"
    }


@router.post("/config/reload")
async def reload_config():
    """Reload all configurations."""
    from transaksional.app.config_loader import reload_configs
    reload_configs()
    
    return {
        "success": True,
        "message": "Configurations reloaded"
    }