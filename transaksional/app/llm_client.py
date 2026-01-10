"""
LLM Client - Improved Extraction
================================
"""

from typing import List, Dict, Optional, Any
from abc import ABC, abstractmethod
import json
import re

from transaksional.app.config import settings


class BaseLLMClient(ABC):
    @abstractmethod
    async def generate(self, messages: List[Dict[str, str]], temperature: float = 0.7,
                      max_tokens: int = 500, json_mode: bool = False) -> str:
        pass
    
    @abstractmethod
    async def extract_fields(self, user_message: str, context: str,
                            available_fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        pass


class OpenAIClient(BaseLLMClient):
    def __init__(self):
        from openai import AsyncOpenAI
        config = settings.llm.get("openai", {})
        self.client = AsyncOpenAI(api_key=config.get("api_key"))
        self.model = config.get("model", "gpt-4o-mini")
        self.default_temperature = config.get("temperature", 0.7)
        self.default_max_tokens = config.get("max_tokens", 500)
    
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
        self.default_temperature = config.get("temperature", 0.7)
        self.default_max_tokens = config.get("max_tokens", 500)
    
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
    async def generate(self, messages: List[Dict[str, str]], temperature: float = 0.7,
                      max_tokens: int = 500, json_mode: bool = False) -> str:
        if json_mode:
            return '{}'
        return "Mock response"
    
    async def extract_fields(self, user_message: str, context: str,
                            available_fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        result = {}
        message_lower = user_message.lower()
        
        # Simple patterns
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


def get_llm_client() -> BaseLLMClient:
    """Get LLM client based on configuration"""
    provider = settings.llm_provider
    
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