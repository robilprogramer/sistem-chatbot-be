"""
Rating System - User Feedback & Ratings
========================================
Features:
- Star rating (1-5)
- Text feedback
- Rating prompts at appropriate times
- Analytics
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import json


class RatingCategory(str, Enum):
    OVERALL = "overall"
    EASE_OF_USE = "ease_of_use"
    RESPONSE_QUALITY = "response_quality"
    SPEED = "speed"
    HELPFULNESS = "helpfulness"


@dataclass
class Rating:
    """User rating"""
    id: Optional[int] = None
    session_id: str = ""
    user_id: Optional[str] = None
    registration_number: Optional[str] = None
    rating: int = 0  # 1-5
    feedback_text: Optional[str] = None
    category: RatingCategory = RatingCategory.OVERALL
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def is_valid(self) -> bool:
        return 1 <= self.rating <= 5
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "registration_number": self.registration_number,
            "rating": self.rating,
            "feedback_text": self.feedback_text,
            "category": self.category.value,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Rating":
        return cls(
            id=data.get("id"),
            session_id=data.get("session_id", ""),
            user_id=data.get("user_id"),
            registration_number=data.get("registration_number"),
            rating=data.get("rating", 0),
            feedback_text=data.get("feedback_text"),
            category=RatingCategory(data.get("category", "overall")),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now()
        )


class RatingPromptType(str, Enum):
    POST_REGISTRATION = "post_registration"
    IDLE_EXIT = "idle_exit"
    PERIODIC = "periodic"
    MANUAL = "manual"


@dataclass
class RatingPrompt:
    """Rating prompt configuration"""
    id: int
    prompt_type: RatingPromptType
    conditions: Dict[str, Any]
    prompt_message: str
    follow_up_message: str = "Terima kasih atas feedback-nya! 🙏"
    is_active: bool = True
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RatingPrompt":
        return cls(
            id=data.get("id", 0),
            prompt_type=RatingPromptType(data.get("prompt_type", "manual")),
            conditions=data.get("conditions", {}),
            prompt_message=data.get("prompt_message", ""),
            follow_up_message=data.get("follow_up_message", "Terima kasih!"),
            is_active=data.get("is_active", True)
        )


class RatingManager:
    """
    Manages user ratings and feedback.
    """
    
    # Rating emoji mapping
    RATING_EMOJIS = {
        1: "😞",
        2: "😕",
        3: "😐",
        4: "🙂",
        5: "😄"
    }
    
    RATING_LABELS = {
        1: "Sangat Tidak Puas",
        2: "Tidak Puas",
        3: "Cukup",
        4: "Puas",
        5: "Sangat Puas"
    }
    
    def __init__(self, db_manager=None):
        self._db = db_manager
        self._prompts: List[RatingPrompt] = []
        self._pending_ratings: Dict[str, Dict] = {}  # session_id -> rating context
        
        self._load_default_prompts()
    
    @property
    def db(self):
        if self._db is None:
            try:
                from transaksional.app.database import get_db_manager
                self._db = get_db_manager()
            except:
                pass
        return self._db
    
    def _load_default_prompts(self):
        """Load default rating prompts"""
        self._prompts = [
            RatingPrompt(
                id=1,
                prompt_type=RatingPromptType.POST_REGISTRATION,
                conditions={"after_completion": True},
                prompt_message="""
🌟 **Bagaimana pengalaman kamu?**

Berikan rating untuk pelayanan chatbot pendaftaran kami:

⭐ 1 - Sangat Tidak Puas
⭐⭐ 2 - Tidak Puas  
⭐⭐⭐ 3 - Cukup
⭐⭐⭐⭐ 4 - Puas
⭐⭐⭐⭐⭐ 5 - Sangat Puas

Ketik angka 1-5 untuk memberikan rating.
""",
                follow_up_message="Terima kasih atas rating-nya! Ada saran atau masukan lain? (Ketik 'skip' untuk lewati)"
            ),
            RatingPrompt(
                id=2,
                prompt_type=RatingPromptType.IDLE_EXIT,
                conditions={"idle_minutes": 30, "min_messages": 3},
                prompt_message="""
Sepertinya kamu akan pergi. Boleh berikan rating sebelum pergi?

Ketik angka 1-5:
1️⃣ Buruk | 2️⃣ Kurang | 3️⃣ Cukup | 4️⃣ Bagus | 5️⃣ Sangat Bagus
""",
                follow_up_message="Terima kasih! 🙏"
            )
        ]
    
    def load_prompts_from_db(self):
        """Load prompts from database"""
        if not self.db:
            return
        
        try:
            prompts = self.db.get_rating_prompts()
            self._prompts = [RatingPrompt.from_dict(p) for p in prompts]
        except Exception as e:
            print(f"Error loading rating prompts: {e}")
    
    def start_rating_flow(self, session_id: str, prompt_type: RatingPromptType,
                          user_id: str = None, registration_number: str = None) -> Optional[str]:
        """
        Start a rating flow for a session.
        Returns the prompt message to show to user.
        """
        # Find matching prompt
        prompt = next((p for p in self._prompts 
                       if p.prompt_type == prompt_type and p.is_active), None)
        
        if not prompt:
            return None
        
        # Check if already prompted
        if session_id in self._pending_ratings:
            return None
        
        # Store pending rating context
        self._pending_ratings[session_id] = {
            "prompt_id": prompt.id,
            "prompt_type": prompt_type.value,
            "user_id": user_id,
            "registration_number": registration_number,
            "started_at": datetime.now().isoformat(),
            "state": "awaiting_rating",  # awaiting_rating -> awaiting_feedback -> completed
            "follow_up_message": prompt.follow_up_message
        }
        
        # Log prompt shown
        if self.db:
            try:
                self.db.log_rating_prompt(
                    session_id=session_id,
                    prompt_id=prompt.id
                )
            except:
                pass
        
        return prompt.prompt_message
    
    def process_rating_input(self, session_id: str, user_input: str) -> Dict[str, Any]:
        """
        Process user input during rating flow.
        Returns dict with 'response' and 'completed' keys.
        """
        if session_id not in self._pending_ratings:
            return {"response": None, "completed": False, "is_rating_input": False}
        
        context = self._pending_ratings[session_id]
        state = context.get("state", "awaiting_rating")
        
        user_input = user_input.strip().lower()
        
        if state == "awaiting_rating":
            # Try to parse rating
            rating = self._parse_rating(user_input)
            
            if rating is None:
                return {
                    "response": "Mohon masukkan angka 1-5 untuk rating.",
                    "completed": False,
                    "is_rating_input": True
                }
            
            # Store rating
            context["rating"] = rating
            context["state"] = "awaiting_feedback"
            
            emoji = self.RATING_EMOJIS.get(rating, "")
            label = self.RATING_LABELS.get(rating, "")
            
            response = f"{emoji} Rating: {rating}/5 ({label})\n\n{context.get('follow_up_message', '')}"
            
            return {
                "response": response,
                "completed": False,
                "is_rating_input": True,
                "rating": rating
            }
        
        elif state == "awaiting_feedback":
            # Process feedback
            feedback = None if user_input in ["skip", "lewati", "tidak", "no", "-"] else user_input
            
            # Save the complete rating
            rating = self._save_rating(session_id, context, feedback)
            
            # Clean up
            del self._pending_ratings[session_id]
            
            if feedback:
                response = f"Terima kasih atas feedback-nya! Masukan kamu sangat berharga bagi kami. 🙏"
            else:
                response = "Terima kasih atas rating-nya! 🙏"
            
            return {
                "response": response,
                "completed": True,
                "is_rating_input": True,
                "rating": context.get("rating"),
                "feedback": feedback
            }
        
        return {"response": None, "completed": False, "is_rating_input": False}
    
    def _parse_rating(self, input_str: str) -> Optional[int]:
        """Parse rating from user input"""
        # Direct number
        try:
            rating = int(input_str)
            if 1 <= rating <= 5:
                return rating
        except ValueError:
            pass
        
        # Text mapping
        text_mapping = {
            "satu": 1, "one": 1,
            "dua": 2, "two": 2,
            "tiga": 3, "three": 3,
            "empat": 4, "four": 4,
            "lima": 5, "five": 5,
            "buruk": 1, "sangat buruk": 1,
            "kurang": 2, "tidak puas": 2,
            "cukup": 3, "biasa": 3,
            "bagus": 4, "puas": 4,
            "sangat bagus": 5, "sangat puas": 5, "excellent": 5
        }
        
        for text, rating in text_mapping.items():
            if text in input_str.lower():
                return rating
        
        # Emoji/star counting
        star_count = input_str.count("⭐") or input_str.count("*")
        if 1 <= star_count <= 5:
            return star_count
        
        return None
    
    def _save_rating(self, session_id: str, context: Dict, feedback: str = None) -> Rating:
        """Save rating to database"""
        rating = Rating(
            session_id=session_id,
            user_id=context.get("user_id"),
            registration_number=context.get("registration_number"),
            rating=context.get("rating", 0),
            feedback_text=feedback,
            category=RatingCategory.OVERALL,
            metadata={
                "prompt_id": context.get("prompt_id"),
                "prompt_type": context.get("prompt_type")
            }
        )
        
        if self.db:
            try:
                rating_id = self.db.save_rating(
                    session_id=rating.session_id,
                    user_id=rating.user_id,
                    registration_number=rating.registration_number,
                    rating=rating.rating,
                    feedback_text=rating.feedback_text,
                    category=rating.category.value,
                    metadata=rating.metadata
                )
                rating.id = rating_id
            except Exception as e:
                print(f"Error saving rating: {e}")
        
        return rating
    
    def cancel_rating_flow(self, session_id: str):
        """Cancel ongoing rating flow"""
        if session_id in self._pending_ratings:
            del self._pending_ratings[session_id]
    
    def is_rating_in_progress(self, session_id: str) -> bool:
        """Check if rating flow is in progress"""
        return session_id in self._pending_ratings
    
    def get_rating_state(self, session_id: str) -> Optional[str]:
        """Get current rating state for session"""
        if session_id in self._pending_ratings:
            return self._pending_ratings[session_id].get("state")
        return None
    
    def submit_rating(self, session_id: str, rating: int, 
                      feedback: str = None, user_id: str = None,
                      registration_number: str = None,
                      category: RatingCategory = RatingCategory.OVERALL) -> Rating:
        """
        Submit a rating directly (without flow).
        """
        rating_obj = Rating(
            session_id=session_id,
            user_id=user_id,
            registration_number=registration_number,
            rating=rating,
            feedback_text=feedback,
            category=category
        )
        
        if not rating_obj.is_valid():
            raise ValueError("Rating must be between 1 and 5")
        
        if self.db:
            try:
                rating_id = self.db.save_rating(
                    session_id=rating_obj.session_id,
                    user_id=rating_obj.user_id,
                    registration_number=rating_obj.registration_number,
                    rating=rating_obj.rating,
                    feedback_text=rating_obj.feedback_text,
                    category=rating_obj.category.value,
                    metadata={}
                )
                rating_obj.id = rating_id
            except Exception as e:
                print(f"Error saving rating: {e}")
        
        return rating_obj
    
    def get_ratings_for_session(self, session_id: str) -> List[Rating]:
        """Get all ratings for a session"""
        if not self.db:
            return []
        
        try:
            ratings = self.db.get_ratings(session_id=session_id)
            return [Rating.from_dict(r) for r in ratings]
        except:
            return []
    
    def get_rating_stats(self, 
                         start_date: datetime = None,
                         end_date: datetime = None) -> Dict[str, Any]:
        """Get rating statistics"""
        if not self.db:
            return {}
        
        try:
            return self.db.get_rating_stats(start_date, end_date)
        except:
            return {}
    
    def get_recent_ratings(self, limit: int = 10) -> List[Rating]:
        """Get recent ratings"""
        if not self.db:
            return []
        
        try:
            ratings = self.db.get_ratings(limit=limit)
            return [Rating.from_dict(r) for r in ratings]
        except:
            return []
    
    def format_rating_summary(self, stats: Dict[str, Any]) -> str:
        """Format rating stats as readable summary"""
        if not stats:
            return "Belum ada data rating."
        
        avg = stats.get("avg_rating", 0)
        total = stats.get("total_ratings", 0)
        positive = stats.get("positive_ratings", 0)
        
        stars = "⭐" * int(round(avg))
        
        return f"""
📊 **Rating Summary**

{stars} {avg:.1f}/5.0

Total Ratings: {total}
Positive (4-5): {positive} ({(positive/total*100) if total > 0 else 0:.0f}%)
"""


# =============================================================================
# SINGLETON
# =============================================================================

_rating_manager: Optional[RatingManager] = None

def get_rating_manager() -> RatingManager:
    global _rating_manager
    if _rating_manager is None:
        _rating_manager = RatingManager()
    return _rating_manager


def init_rating_manager(db_manager=None) -> RatingManager:
    """Initialize rating manager with dependencies"""
    global _rating_manager
    _rating_manager = RatingManager(db_manager=db_manager)
    
    try:
        _rating_manager.load_prompts_from_db()
    except:
        pass
    
    return _rating_manager