"""
Escalation Detector - Deteksi kapan perlu eskalasi ke CS

File: cs/escalation.py
"""

import re
from typing import Optional, Tuple, List
from .schemas import EscalationReason


class EscalationDetector:
    """
    Detector untuk menentukan kapan chat perlu di-eskalasi ke CS
    
    Triggers:
    1. Explicit request - User langsung minta bicara CS
    2. Low confidence - Bot tidak yakin dengan jawaban
    3. Loop detected - Bot memberikan jawaban berulang
    4. Negative sentiment - User menunjukkan frustasi
    """
    
    # Keywords yang menandakan user ingin bicara CS
    CS_REQUEST_KEYWORDS = [
        # Explicit CS request
        r'\bbicara\s*(dengan\s*)?(cs|customer\s*service|admin|operator|manusia|orang)\b',
        r'\bhubungi\s*(cs|customer\s*service|admin|operator)\b',
        r'\bminta\s*(cs|customer\s*service|admin|operator)\b',
        r'\bconnect\s*(to\s*)?(cs|customer\s*service|admin|human|agent)\b',
        r'\btalk\s*(to\s*)?(cs|customer\s*service|admin|human|agent)\b',
        r'\bspeak\s*(to\s*)?(cs|customer\s*service|admin|human|agent)\b',
        
        # Frustration leading to CS request
        r'\bbosan\s*(dengan\s*)?bot\b',
        r'\bbot\s*(nya\s*)?(bodoh|gak\s*ngerti|tidak\s*mengerti)\b',
        r'\bmau\s*(bicara\s*)?(sama\s*)?orang\s*(asli|beneran)\b',
        r'\bbutuh\s*bantuan\s*(dari\s*)?(manusia|orang)\b',
        
        # Simple keywords (case insensitive)
        r'^cs$',
        r'^operator$',
        r'^admin$',
        r'^customer\s*service$',
    ]
    
    # Keywords yang menandakan frustasi
    FRUSTRATION_KEYWORDS = [
        r'\b(kesal|frustasi|marah|bete|sebel|capek|cape)\b',
        r'\b(gak|tidak|ga)\s*(ngerti|paham|mengerti|jelas)\b',
        r'\b(jawaban|respon)\s*(nya\s*)?(gak|tidak)\s*(membantu|jelas|nyambung)\b',
        r'\budah\s*(berapa\s*)?(kali|x)\b',
        r'\b(tolong|please)\s*(dong|deh)\b',
        r'\bhelp\s*me\b',
    ]
    
    # Threshold untuk low confidence
    LOW_CONFIDENCE_THRESHOLD = 0.4
    
    # Jumlah response serupa untuk detect loop
    LOOP_DETECTION_COUNT = 3
    
    def __init__(self):
        # Compile regex patterns
        self.cs_patterns = [re.compile(p, re.IGNORECASE) for p in self.CS_REQUEST_KEYWORDS]
        self.frustration_patterns = [re.compile(p, re.IGNORECASE) for p in self.FRUSTRATION_KEYWORDS]
        
        # Track recent responses untuk loop detection
        self.recent_responses: dict = {}  # user_id -> list of responses
    
    def check_explicit_cs_request(self, message: str) -> bool:
        """Check apakah user explicitly minta CS"""
        message_lower = message.lower().strip()
        
        for pattern in self.cs_patterns:
            if pattern.search(message_lower):
                return True
        
        return False
    
    def check_frustration(self, message: str) -> bool:
        """Check apakah user menunjukkan frustasi"""
        for pattern in self.frustration_patterns:
            if pattern.search(message):
                return True
        return False
    
    def check_low_confidence(self, confidence: float) -> bool:
        """Check apakah bot confidence rendah"""
        return confidence < self.LOW_CONFIDENCE_THRESHOLD
    
    def check_loop_detected(self, user_id: str, current_response: str) -> bool:
        """
        Check apakah bot memberikan jawaban berulang
        
        Simplified: check if same/similar response given multiple times
        """
        if user_id not in self.recent_responses:
            self.recent_responses[user_id] = []
        
        responses = self.recent_responses[user_id]
        
        # Simple similarity check (exact match)
        similar_count = sum(1 for r in responses[-5:] if self._is_similar(r, current_response))
        
        # Add current response
        responses.append(current_response)
        
        # Keep only last 10 responses
        if len(responses) > 10:
            self.recent_responses[user_id] = responses[-10:]
        
        return similar_count >= self.LOOP_DETECTION_COUNT
    
    def _is_similar(self, response1: str, response2: str, threshold: float = 0.8) -> bool:
        """Simple similarity check"""
        # Normalize
        r1 = response1.lower().strip()
        r2 = response2.lower().strip()
        
        # Exact match
        if r1 == r2:
            return True
        
        # Check if one contains significant portion of the other
        words1 = set(r1.split())
        words2 = set(r2.split())
        
        if not words1 or not words2:
            return False
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        jaccard = len(intersection) / len(union) if union else 0
        
        return jaccard >= threshold
    
    def detect(
        self, 
        message: str, 
        user_id: str,
        bot_response: Optional[str] = None,
        confidence: Optional[float] = None
    ) -> Tuple[bool, Optional[EscalationReason]]:
        """
        Main detection method
        
        Returns:
            Tuple[should_escalate, reason]
        """
        # 1. Check explicit CS request (highest priority)
        if self.check_explicit_cs_request(message):
            return True, EscalationReason.EXPLICIT_REQUEST
        
        # 2. Check low confidence
        if confidence is not None and self.check_low_confidence(confidence):
            return True, EscalationReason.LOW_CONFIDENCE
        
        # 3. Check loop detection
        if bot_response and self.check_loop_detected(user_id, bot_response):
            return True, EscalationReason.LOOP_DETECTED
        
        # 4. Check frustration
        if self.check_frustration(message):
            return True, EscalationReason.SENTIMENT_NEGATIVE
        
        return False, None
    
    def clear_user_history(self, user_id: str):
        """Clear response history untuk user (setelah session selesai)"""
        if user_id in self.recent_responses:
            del self.recent_responses[user_id]


# Singleton instance
_escalation_detector: Optional[EscalationDetector] = None


def get_escalation_detector() -> EscalationDetector:
    """Get singleton escalation detector"""
    global _escalation_detector
    if _escalation_detector is None:
        _escalation_detector = EscalationDetector()
    return _escalation_detector