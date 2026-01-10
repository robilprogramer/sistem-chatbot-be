"""
Informational Chatbot Client
============================
Client untuk mengintegrasikan API chatbot informational (RAG-based)
ke dalam sistem transactional.

Chatbot informational menjawab pertanyaan umum seperti:
- Apa saja program yang tersedia?
- Berapa biaya pendaftaran?
- Apa syarat pendaftaran?
- dll
"""

import aiohttp
import asyncio
from typing import Optional, Dict, Any
from dataclasses import dataclass

from transaksional.app.config import get_app_config


@dataclass
class InformationalResponse:
    """Response dari API informational"""
    answer: str
    sources: list = None
    confidence: float = 0.0
    success: bool = True
    error: Optional[str] = None


class InformationalClient:
    """
    Client untuk berkomunikasi dengan API Chatbot Informational (RAG)
    """
    
    def __init__(self, base_url: str = None, api_key: str = None, timeout: int = 30):
        """
        Initialize client
        
        Args:
            base_url: URL API informational (e.g., http://localhost:8080/api/v1)
            api_key: API key jika diperlukan
            timeout: Timeout dalam detik
        """
        config = get_app_config()
        informational_config = config.get("informational_api", {})
        
        self.base_url = base_url or informational_config.get("base_url", "http://localhost:8080/api/v1")
        self.api_key = api_key or informational_config.get("api_key", "")
        self.timeout = timeout or informational_config.get("timeout", 30)
        self.enabled = informational_config.get("enabled", True)
        
        # Endpoint untuk chat informational
        self.chat_endpoint = informational_config.get("chat_endpoint", "/chat")
        
    def _get_headers(self) -> Dict[str, str]:
        """Get headers untuk API request"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    
    async def ask(
        self, 
        question: str, 
        session_id: Optional[str] = None
    ) -> InformationalResponse:
        """
        Kirim pertanyaan ke API informational (RAG)
        
        Args:
            question: Pertanyaan yang sudah di-enrich oleh LLM
            session_id: Session ID untuk tracking
            
        Returns:
            InformationalResponse dengan jawaban
        """
        if not self.enabled:
            return InformationalResponse(
                answer="",
                success=False,
                error="Informational API disabled"
            )
        
        try:
            url = f"{self.base_url.rstrip('/')}{self.chat_endpoint}"
            
            payload = {
                "message": question,
            }
            
            if session_id:
                payload["session_id"] = session_id
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Parse response - sesuaikan dengan format API Anda
                        return InformationalResponse(
                            answer=data.get("response", data.get("answer", data.get("message", ""))),
                            sources=data.get("sources", data.get("references", [])),
                            confidence=data.get("confidence", data.get("score", 1.0)),
                            success=True
                        )
                    else:
                        error_text = await response.text()
                        return InformationalResponse(
                            answer="",
                            success=False,
                            error=f"API error: {response.status} - {error_text}"
                        )
                        
        except asyncio.TimeoutError:
            return InformationalResponse(
                answer="",
                success=False,
                error="Request timeout"
            )
        except aiohttp.ClientError as e:
            return InformationalResponse(
                answer="",
                success=False,
                error=f"Connection error: {str(e)}"
            )
        except Exception as e:
            return InformationalResponse(
                answer="",
                success=False,
                error=f"Unexpected error: {str(e)}"
            )
    
    async def health_check(self) -> bool:
        """
        Check apakah API informational tersedia
        """
        try:
            url = f"{self.base_url.rstrip('/')}/health"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return response.status == 200
        except:
            return False


# Singleton instance
_informational_client: Optional[InformationalClient] = None


def get_informational_client() -> InformationalClient:
    """Get singleton informational client"""
    global _informational_client
    if _informational_client is None:
        _informational_client = InformationalClient()
    return _informational_client


# Convenience function
async def ask_informational(question: str, session_id: str = None) -> InformationalResponse:
    """
    Shortcut untuk bertanya ke API informational
    
    Args:
        question: Pertanyaan user
        session_id: Session ID
        
    Returns:
        InformationalResponse
    """
    client = get_informational_client()
    return await client.ask(question, session_id)
