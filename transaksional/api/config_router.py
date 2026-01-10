from typing import Optional

from fastapi import APIRouter

from transaksional.app.config import settings
from transaksional.app.form_manager import get_form_manager

router = APIRouter(
    prefix=f"{settings.transactional_prefix}/config",
    tags=["Configuration"]
)


@router.get("/steps")
async def get_steps():
    """Get all registration steps configuration."""
    form_manager = get_form_manager()
    steps = form_manager.get_steps()
    
    return {
        "steps": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "order": s.order,
                "is_mandatory": s.is_mandatory,
                "icon": s.raw_config.get("icon", "")
            }
            for s in steps
        ]
    }


@router.get("/fields")
async def get_fields(step: Optional[str] = None):
    """Get form fields, optionally filtered by step."""
    form_manager = get_form_manager()
    
    if step:
        fields = form_manager.get_fields_for_step(step)
    else:
        fields = []
        for s in form_manager.get_steps():
            fields.extend(form_manager.get_fields_for_step(s.id))
    
    return {
        "fields": [
            {
                "id": f.id,
                "label": f.label,
                "step": f.step,
                "type": f.type,
                "is_mandatory": f.is_mandatory,
                "examples": f.examples
            }
            for f in fields
        ]
    }