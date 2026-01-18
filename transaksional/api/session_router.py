"""
Session Router - Fixed Version
Handles session without relying on session.messages attribute
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from transaksional.app.config import settings
from transaksional.app.form_manager import get_form_manager
from transaksional.app.session_state import get_session_manager
from transaksional.app.database import get_db_manager


router = APIRouter(
    prefix=f"{settings.transactional_prefix}/session",
    tags=["Session"]
)

# =============================================================================
# RESPONSE MODELS
# =============================================================================

class SessionActivityItem(BaseModel):
    session_id: str
    user_id: Optional[str]
    last_activity_at: Optional[str]
    last_message_at: Optional[str]
    current_step: Optional[str]
    completion_percentage: float
    is_idle: bool
    idle_since: Optional[str]
    total_idle_triggers: int
    step_name: Optional[str] = None


class UserSessionsResponse(BaseModel):
    user_id: str
    total_sessions: int
    active_sessions: int
    sessions: List[SessionActivityItem]


# =============================================================================
# BASIC SESSION ENDPOINTS
# =============================================================================

@router.post("/new")
async def create_session(user_id: Optional[str] = None):
    form_manager = get_form_manager()
    session_manager = get_session_manager()

    first_step = form_manager.get_first_step()
    session = session_manager.create_session(
        initial_step=first_step.id if first_step else ""
    )

    # Link session to user if provided
    if user_id:
        link_session_to_user(session.session_id, user_id, first_step.id if first_step else "")

    welcome = form_manager.get_welcome_message()

    steps = form_manager.get_steps()

    return {
        "session_id": session.session_id,
        "message": welcome,
        "current_step": session.current_step,
        "step_info": {
            "current": session.current_step,
            "current_index": 0,
            "total_steps": len(steps),
            "steps": [
                {
                    "id": s.id,
                    "name": s.name,
                    "icon": s.raw_config.get("icon", "")
                }
                for s in steps
            ]
        }
    }


@router.get("/{session_id}")
async def get_session(session_id: str):
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
            "current_index": form_manager.get_step_index(session.current_step),
            "current": session.current_step,
            "total_steps": len(steps),
            "steps": [{"id": s.id, "name": s.name} for s in steps]
        }
    }


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    get_session_manager().delete_session(session_id)
    return {"message": "Session deleted"}


# =============================================================================
# DATABASE HELPERS
# =============================================================================

def link_session_to_user(session_id: str, user_id: str, current_step: str = ""):
    """Link session to user and initialize session_activity record."""
    db = get_db_manager()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO session_activity (session_id, user_id, current_step, last_activity_at, completion_percentage)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP, 0)
            ON CONFLICT (session_id)
            DO UPDATE SET
                user_id = EXCLUDED.user_id,
                current_step = EXCLUDED.current_step,
                last_activity_at = CURRENT_TIMESTAMP
            """,
            (session_id, user_id, current_step)
        )


# =============================================================================
# USER SESSION ENDPOINTS
# =============================================================================

@router.get("/user/{user_id}/sessions")
async def get_user_sessions(
    user_id: str,
    include_completed: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
) -> UserSessionsResponse:
    """Get all sessions for a user."""
    
    db = get_db_manager()
    form_manager = get_form_manager()

    steps = form_manager.get_steps()
    step_map = {s.id: s.name for s in steps}

    with db.get_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        completion_filter = "" if include_completed else "AND completion_percentage < 100"

        cursor.execute(
            f"""
            SELECT
                session_id,
                user_id,
                last_activity_at,
                last_message_at,
                current_step,
                COALESCE(completion_percentage, 0) AS completion_percentage,
                COALESCE(is_idle, FALSE) AS is_idle,
                idle_since,
                COALESCE(total_idle_triggers, 0) AS total_idle_triggers
            FROM session_activity
            WHERE user_id = %s {completion_filter}
            ORDER BY last_activity_at DESC NULLS LAST
            LIMIT %s OFFSET %s
            """,
            (user_id, limit, offset)
        )
        rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE completion_percentage < 100) AS active
            FROM session_activity
            WHERE user_id = %s
            """,
            (user_id,)
        )
        count_row = cursor.fetchone()

    sessions = [
        SessionActivityItem(
            session_id=row["session_id"],
            user_id=row["user_id"],
            last_activity_at=row["last_activity_at"].isoformat() if row["last_activity_at"] else None,
            last_message_at=row["last_message_at"].isoformat() if row["last_message_at"] else None,
            current_step=row["current_step"],
            completion_percentage=float(row["completion_percentage"] or 0),
            is_idle=bool(row["is_idle"]),
            idle_since=row["idle_since"].isoformat() if row["idle_since"] else None,
            total_idle_triggers=int(row["total_idle_triggers"] or 0),
            step_name=step_map.get(row["current_step"], row["current_step"])
        )
        for row in rows
    ]

    return UserSessionsResponse(
        user_id=user_id,
        total_sessions=count_row["total"] if count_row else 0,
        active_sessions=count_row["active"] if count_row else 0,
        sessions=sessions
    )


@router.get("/user/{user_id}/active-count")
async def get_user_active_sessions_count(user_id: str):
    """Get count of active (incomplete) sessions for a user."""
    db = get_db_manager()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM session_activity
            WHERE user_id = %s AND completion_percentage < 100
            """,
            (user_id,)
        )
        count = cursor.fetchone()[0]

    return {
        "user_id": user_id,
        "active_sessions": count
    }