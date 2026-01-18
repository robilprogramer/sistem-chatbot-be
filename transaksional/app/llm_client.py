"""
LLM Client - With Vision Support for Document Classification
============================================================
Features:
- Text extraction from user messages
- Image/Vision analysis for document classification
- Multi-provider support (OpenAI, Anthropic)
"""

from typing import List, Dict, Optional, Any
from abc import ABC, abstractmethod
import json
import re
import base64

from transaksional.app.config import settings


class BaseLLMClient(ABC):
    @abstractmethod
    async def explain_examples(self, field: Dict[str, Any], examples: List[str],
                               user_message: str, context: str) -> str:
        """
        Beri penjelasan / contoh untuk sebuah field berdasarkan contoh yang tersedia.
        field: dict dengan id, label, type, ...
        examples: list contoh dari DB
        user_message: isi pesan user yang minta contoh (dipakai untuk konteks)
        context: chat context (recent messages)
        """
        pass

    @abstractmethod
    async def generate(self, messages: List[Dict[str, str]], temperature: float = 0.7,
                      max_tokens: int = 500, json_mode: bool = False) -> str:
        pass
    
    @abstractmethod
    async def extract_fields(self, user_message: str, context: str,
                            available_fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def analyze_image(self, image_base64: str, media_type: str, 
                           prompt: str) -> Optional[str]:
        """Analyze image using vision capabilities"""
        pass


class OpenAIClient(BaseLLMClient):
    def __init__(self):
        from openai import AsyncOpenAI
        config = settings.llm.get("openai", {})
        self.client = AsyncOpenAI(api_key=config.get("api_key"))
        self.model = config.get("model", "gpt-4o-mini")
        self.vision_model = config.get("vision_model", "gpt-4o-mini")  # or gpt-4o for better vision
        self.default_temperature = config.get("temperature", 0.7)
        self.default_max_tokens = config.get("max_tokens", 500)
    
    async def explain_examples(self, field: Dict[str, Any], examples: List[str],
                               user_message: str, context: str) -> str:
        # build prompt
        examples_text = "\n".join([f"- {e}" for e in examples[:10]])  # batasi ke 10
        system_prompt = (
            f"Kamu adalah asisten pendaftaran. User menanyakan contoh untuk field: "
            f"'{field.get('label')}' (id: {field.get('id')}).\n"
            f"Berikan jawaban singkat, ramah, dan kontekstual. "
            f"Jika user meminta lebih banyak contoh, sebutkan bahwa ada contoh lain dan bagaimana meminta."
        )
        user_prompt = (
            f"Pesan user: \"{user_message}\"\n\n"
            f"Contoh yang tersedia untuk field '{field.get('label')}':\n{examples_text}\n\n"
            "Jawab dengan bahasa Indonesia. Tampilkan contoh sebagai daftar, "
            "dan beri instruksi singkat bagaimana user bisa memilih/menyalin contoh."
        )
        try:
            response = await self.generate(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=200,
            )
            return response.strip()
        except Exception as e:
            print(f"OpenAI explain_examples error: {e}")
            # fallback simple
            if examples:
                return "Contoh:\n" + "\n".join([f"- {e}" for e in examples[:5]])
            return "Maaf, contoh tidak tersedia saat ini."

    async def generate(self, messages: List[Dict[str, str]], temperature: float = None,
                      max_tokens: int = None, json_mode: bool = False) -> str:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.default_temperature,
            "max_tokens": max_tokens or self.default_max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content.strip()
    
    async def analyze_image(self, image_base64: str, media_type: str, 
                           prompt: str) -> Optional[str]:
        """
        Analyze image using OpenAI Vision API.
        
        Args:
            image_base64: Base64 encoded image data
            media_type: MIME type (image/jpeg, image/png, etc.)
            prompt: Analysis prompt
            
        Returns:
            Analysis result as string, or None if failed
        """
        try:
            # Build image URL for OpenAI format
            image_url = f"data:{media_type};base64,{image_base64}"
            
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url,
                                "detail": "low"  # Use "high" for better accuracy but slower
                            }
                        }
                    ]
                }
            ]
            
            response = await self.client.chat.completions.create(
                model=self.vision_model,
                messages=messages,
                max_tokens=300,
                temperature=0.1
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"OpenAI Vision error: {e}")
            return None
    
    async def extract_fields(self, user_message: str, context: str,
                            available_fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Build field description with examples
        field_desc = []
        for f in available_fields:
            desc = f"- {f['id']}: {f['label']} (type: {f['type']})"
            if f.get('examples'):
                desc += f" contoh: {f['examples'][0]}"
            if f.get('options'):
                opts = [o.get('value', '') for o in f['options'][:5]]
                desc += f" pilihan: {', '.join(opts)}"
            field_desc.append(desc)
        
        field_desc_str = "\n".join(field_desc)
        
        system_prompt = f"""Kamu adalah AI yang mengekstrak informasi dari pesan user untuk form pendaftaran sekolah.

FIELD YANG TERSEDIA:
{field_desc_str}

ATURAN PENTING:
1. Extract HANYA nilai murni yang disebutkan user
2. JANGAN PERNAH menyertakan nama field/label dalam nilai
3. Contoh BENAR:
   - User: "nama saya Ahmad Fauzi" → {{"nama_lengkap": "Ahmad Fauzi"}}
   - User: "lahir di Jakarta 15 Mei 2000" → {{"tempat_lahir": "Jakarta", "tanggal_lahir": "15/05/2000"}}
   - User: "ayah budi ibu siti" → {{"nama_ayah": "Budi", "nama_ibu": "Siti"}}
   
4. Contoh SALAH (JANGAN LAKUKAN):
   - {{"nama_lengkap": "Nama Lengkap Siswa: Ahmad"}} ← SALAH!
   - {{"alamat": "Alamat Lengkap: Jl Sudirman"}} ← SALAH!
   
5. Normalize nilai:
   - Gender: "Laki-laki" atau "Perempuan"
   - Tanggal: format DD/MM/YYYY
   - Telepon: angka saja (0812xxx)
   - Capitalize nama dengan benar

6. Jika user menyebut beberapa data sekaligus, extract semua
7. Return HANYA JSON object tanpa penjelasan"""

        user_prompt = f'PESAN USER: "{user_message}"\n\nExtract ke JSON:'
        
        try:
            response = await self.generate(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                json_mode=True
            )
            
            result = json.loads(response)
            
            # Post-process: clean up values that might include labels
            cleaned = {}
            for key, value in result.items():
                if isinstance(value, str):
                    # Remove patterns like "Label : value" or "Label: value"
                    cleaned_value = re.sub(r'^[^:]+:\s*', '', value).strip()
                    # Remove common prefixes
                    prefixes = ["nama lengkap", "tempat lahir", "alamat lengkap", "nama ayah", "nama ibu"]
                    for prefix in prefixes:
                        if cleaned_value.lower().startswith(prefix):
                            cleaned_value = cleaned_value[len(prefix):].strip(" :")
                    cleaned[key] = cleaned_value.strip() if cleaned_value else value
                else:
                    cleaned[key] = value
            
            return cleaned
            
        except json.JSONDecodeError:
            match = re.search(r'\{[^}]+\}', response if 'response' in dir() else '')
            if match:
                try:
                    return json.loads(match.group())
                except:
                    pass
            return {}
        except Exception as e:
            print(f"Extract fields error: {e}")
            return {}


class AnthropicClient(BaseLLMClient):
    def __init__(self):
        from anthropic import AsyncAnthropic
        config = settings.llm.get("anthropic", {})
        self.client = AsyncAnthropic(api_key=config.get("api_key"))
        self.model = config.get("model", "claude-3-sonnet-20240229")
        self.vision_model = config.get("vision_model", "claude-3-sonnet-20240229")
        self.default_temperature = config.get("temperature", 0.7)
        self.default_max_tokens = config.get("max_tokens", 500)
    async def explain_examples(self, field: Dict[str, Any], examples: List[str],
                               user_message: str, context: str) -> str:
        examples_text = "\n".join([f"- {e}" for e in examples[:10]])
        system_prompt = (
            f"User meminta contoh untuk field '{field.get('label')}'. "
            "Jawab singkat dan ramah dalam bahasa Indonesia, tampilkan contoh sebagai daftar."
        )
        user_prompt = f"Pesan user: \"{user_message}\"\n\nContoh:\n{examples_text}"
        try:
            response = await self.generate(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=200,
                json_mode=False
            )
            return response.strip()
        except Exception as e:
            print(f"Anthropic explain_examples error: {e}")
            return "Contoh:\n" + ("\n".join(examples[:5]) if examples else "Tidak ada contoh.")

    async def generate(self, messages: List[Dict[str, str]], temperature: float = None,
                      max_tokens: int = None, json_mode: bool = False) -> str:
        system_message = ""
        conversation = []
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                conversation.append({"role": msg["role"], "content": msg["content"]})
        
        if json_mode:
            system_message += "\n\nIMPORTANT: Respond with valid JSON only, no other text."
        
        response = await self.client.messages.create(
            model=self.model,
            system=system_message,
            messages=conversation,
            temperature=temperature or self.default_temperature,
            max_tokens=max_tokens or self.default_max_tokens,
        )
        return response.content[0].text.strip()
    
    async def analyze_image(self, image_base64: str, media_type: str, 
                           prompt: str) -> Optional[str]:
        """
        Analyze image using Anthropic Claude Vision API.
        
        Args:
            image_base64: Base64 encoded image data
            media_type: MIME type (image/jpeg, image/png, etc.)
            prompt: Analysis prompt
            
        Returns:
            Analysis result as string, or None if failed
        """
        try:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
            
            response = await self.client.messages.create(
                model=self.vision_model,
                messages=messages,
                max_tokens=300,
                temperature=0.1
            )
            
            return response.content[0].text.strip()
            
        except Exception as e:
            print(f"Anthropic Vision error: {e}")
            return None
    
    async def extract_fields(self, user_message: str, context: str,
                            available_fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        field_desc = []
        for f in available_fields:
            desc = f"- {f['id']}: {f['label']} (type: {f['type']})"
            if f.get('examples'):
                desc += f" contoh: {f['examples'][0]}"
            field_desc.append(desc)
        
        field_desc_str = "\n".join(field_desc)
        
        system_prompt = f"""Extract informasi dari pesan user ke JSON.

FIELD TERSEDIA:
{field_desc_str}

ATURAN:
1. Extract HANYA nilai murni, TANPA nama field
2. Contoh benar: {{"nama_lengkap": "Ahmad"}}
3. Contoh salah: {{"nama_lengkap": "Nama Lengkap: Ahmad"}}"""
        
        try:
            response = await self.generate(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f'Message: "{user_message}"'}
                ],
                temperature=0.1,
                json_mode=True
            )
            
            result = json.loads(response)
            
            # Post-process
            cleaned = {}
            for key, value in result.items():
                if isinstance(value, str):
                    cleaned_value = re.sub(r'^[^:]+:\s*', '', value).strip()
                    cleaned[key] = cleaned_value if cleaned_value else value
                else:
                    cleaned[key] = value
            
            return cleaned
        except:
            return {}


class MockLLMClient(BaseLLMClient):
    """Mock client for testing without API calls"""
    
    async def generate(self, messages: List[Dict[str, str]], temperature: float = 0.7,
                      max_tokens: int = 500, json_mode: bool = False) -> str:
        if json_mode:
            return '{}'
        return "Mock response"
    async def explain_examples(self, field: Dict[str, Any], examples: List[str],
                               user_message: str, context: str) -> str:
        if not examples:
            return f"Tidak ada contoh tersimpan untuk {field.get('label')}."
        # return up to 5 contoh
        return f"Contoh {field.get('label')}:\n" + "\n".join([f"- {e}" for e in examples[:5]])

    async def analyze_image(self, image_base64: str, media_type: str, 
                           prompt: str) -> Optional[str]:
        """Mock image analysis - returns unknown for testing"""
        return '{"type": "unknown", "confidence": 0.0, "reason": "Mock client"}'
    
    async def extract_fields(self, user_message: str, context: str,
                            available_fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        result = {}
        message_lower = user_message.lower()
        
        # Simple patterns for basic extraction
        patterns = {
            "nama_lengkap": r"(?:nama\s+(?:saya\s+)?(?:adalah\s+)?|saya\s+)([A-Za-z\s]+?)(?:,|\.|$|lahir|tempat|tanggal)",
            "tempat_lahir": r"(?:lahir\s+(?:di\s+)?|tempat\s+lahir\s*:?\s*)([A-Za-z]+)",
            "tanggal_lahir": r"(\d{1,2}[-/]\d{1,2}[-/]\d{4}|\d{1,2}\s+\w+\s+\d{4})",
        }
        
        for field_id, pattern in patterns.items():
            if any(f["id"] == field_id for f in available_fields):
                match = re.search(pattern, user_message, re.IGNORECASE)
                if match:
                    result[field_id] = match.group(1).strip().title()
        
        return result


class HybridLLMClient(BaseLLMClient):
    """
    Hybrid client that can use different providers for different tasks.
    Example: Use OpenAI for vision, Anthropic for text.
    """
    
    def __init__(self):
        config = settings.llm
        
        # Primary client for text
        self.text_provider = config.get("text_provider", settings.llm_provider)
        # Vision client (might be different)
        self.vision_provider = config.get("vision_provider", settings.llm_provider)
        
        self._text_client = None
        self._vision_client = None
    
    def _get_client(self, provider: str) -> BaseLLMClient:
        """Get client instance for provider"""
        if provider == "openai":
            return OpenAIClient()
        elif provider == "anthropic":
            return AnthropicClient()
        else:
            return MockLLMClient()
    
    @property
    def text_client(self) -> BaseLLMClient:
        if self._text_client is None:
            self._text_client = self._get_client(self.text_provider)
        return self._text_client
    
    @property
    def vision_client(self) -> BaseLLMClient:
        if self._vision_client is None:
            self._vision_client = self._get_client(self.vision_provider)
        return self._vision_client
    
    async def generate(self, messages: List[Dict[str, str]], temperature: float = 0.7,
                      max_tokens: int = 500, json_mode: bool = False) -> str:
        return await self.text_client.generate(messages, temperature, max_tokens, json_mode)
    
    async def analyze_image(self, image_base64: str, media_type: str, 
                           prompt: str) -> Optional[str]:
        return await self.vision_client.analyze_image(image_base64, media_type, prompt)
    
    async def extract_fields(self, user_message: str, context: str,
                            available_fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        return await self.text_client.extract_fields(user_message, context, available_fields)


def get_llm_client() -> BaseLLMClient:
    """Get LLM client based on configuration"""
    provider = settings.llm_provider
    
    # Check if hybrid mode is enabled
    if settings.llm.get("hybrid_mode", False):
        return HybridLLMClient()
    
    if provider == "openai":
        return OpenAIClient()
    elif provider == "anthropic":
        return AnthropicClient()
    elif provider == "mock":
        return MockLLMClient()
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


_llm_client: Optional[BaseLLMClient] = None


def get_llm() -> BaseLLMClient:
    """Get singleton LLM client"""
    global _llm_client
    if _llm_client is None:
        _llm_client = get_llm_client()
    return _llm_client


def reset_llm_client():
    """Reset LLM client (useful for testing or config changes)"""
    global _llm_client
    _llm_client = None