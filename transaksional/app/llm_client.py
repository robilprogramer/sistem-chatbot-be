"""
LLM Client - Enhanced with Contextual Understanding
====================================================
Features:
- Text extraction from user messages
- Image/Vision analysis for document classification
- Multi-provider support (OpenAI, Anthropic)
- CONTEXTUAL UNDERSTANDING untuk pendaftaran

CARA PAKAI:
- Replace file llm_client.py existing dengan file ini
- Atau merge method-method baru ke file existing
"""

from typing import List, Dict, Optional, Any
from abc import ABC, abstractmethod
import json
import re
import base64

from transaksional.app.config import settings


# =============================================================================
# BASE CLASS
# =============================================================================

class BaseLLMClient(ABC):
    """Base class untuk LLM clients"""
    
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
    
    @abstractmethod
    async def explain_examples(self, field: Dict[str, Any], examples: List[str],
                               user_message: str, context: str) -> str:
        """Explain examples for a field"""
        pass
    
    # =========================================================================
    # NEW: Contextual Understanding Methods
    # =========================================================================
    
    @abstractmethod
    async def process_contextual_message(
        self,
        user_message: str,
        session_context: Dict[str, Any],
        available_fields: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Process user message with full session context.
        
        Returns:
            {
                "intent": "data_input" | "question" | "command" | "clarification" | "greeting",
                "extracted_fields": {...},
                "suggested_response": "...",
                "confidence": 0.0-1.0,
                "next_field_hint": "..."
            }
        """
        pass


# =============================================================================
# OPENAI CLIENT
# =============================================================================

class OpenAIClient(BaseLLMClient):
    """OpenAI client dengan contextual understanding"""
    
    def __init__(self):
        from openai import AsyncOpenAI
        config = settings.llm.get("openai", {})
        self.client = AsyncOpenAI(api_key=config.get("api_key"))
        self.model = config.get("model", "gpt-4o-mini")
        self.vision_model = config.get("vision_model", "gpt-4o-mini")
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
    
    async def analyze_image(self, image_base64: str, media_type: str, 
                           prompt: str) -> Optional[str]:
        """Analyze image using OpenAI Vision API"""
        try:
            image_url = f"data:{media_type};base64,{image_base64}"
            
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url, "detail": "low"}
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
    
    async def explain_examples(self, field: Dict[str, Any], examples: List[str],
                               user_message: str, context: str) -> str:
        """Explain examples for a field"""
        examples_text = "\n".join([f"- {e}" for e in examples[:10]])
        system_prompt = (
            f"Kamu adalah asisten pendaftaran. User menanyakan contoh untuk field: "
            f"'{field.get('label')}' (id: {field.get('id')}).\n"
            f"Berikan jawaban singkat, ramah, dan kontekstual dalam bahasa Indonesia."
        )
        user_prompt = (
            f"Pesan user: \"{user_message}\"\n\n"
            f"Contoh yang tersedia untuk field '{field.get('label')}':\n{examples_text}\n\n"
            "Tampilkan contoh sebagai daftar dan beri instruksi singkat."
        )
        try:
            response = await self.generate(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=250,
            )
            return response.strip()
        except Exception as e:
            print(f"OpenAI explain_examples error: {e}")
            if examples:
                return "Contoh:\n" + "\n".join([f"• {e}" for e in examples[:5]])
            return "Maaf, contoh tidak tersedia saat ini."
    
    async def extract_fields(self, user_message: str, context: str,
                            available_fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract field values from user message"""
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
   
4. Contoh SALAH (JANGAN LAKUKAN):
   - {{"nama_lengkap": "Nama Lengkap Siswa: Ahmad"}} ← SALAH!
   
5. Normalize nilai:
   - Gender: "Laki-laki" atau "Perempuan"
   - Tanggal: format DD/MM/YYYY
   - Telepon: angka saja (0812xxx)

6. Return HANYA JSON object tanpa penjelasan
7. Return {{}} jika tidak ada data yang bisa diextract"""

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
            
            # Post-process: clean up values
            cleaned = {}
            for key, value in result.items():
                if isinstance(value, str):
                    cleaned_value = re.sub(r'^[^:]+:\s*', '', value).strip()
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
    
    # =========================================================================
    # NEW: Contextual Understanding Methods
    # =========================================================================
    
    def _build_session_context_prompt(self, session_context: Dict[str, Any]) -> str:
        """Build detailed session context for LLM"""
        
        current_step = session_context.get("current_step", {})
        collected_data = session_context.get("collected_data", {})
        missing_fields = session_context.get("missing_fields", [])
        completion = session_context.get("completion_percentage", 0)
        phase = session_context.get("phase", "collecting")
        
        # Format collected data
        collected_str = ""
        if collected_data:
            items = []
            for field_id, value in collected_data.items():
                if not field_id.startswith("_"):
                    items.append(f"  - {field_id}: {value}")
            collected_str = "\n".join(items) if items else "  (belum ada data)"
        else:
            collected_str = "  (belum ada data)"
        
        # Format missing fields
        missing_str = ""
        if missing_fields:
            missing_items = []
            for f in missing_fields[:5]:
                label = f.get('label', f.get('id', 'Unknown'))
                missing_items.append(f"  - {label}")
            missing_str = "\n".join(missing_items)
        else:
            missing_str = "  (semua data wajib sudah lengkap)"
        
        context_prompt = f"""
=== KONTEKS SESI PENDAFTARAN ===

📍 TAHAP SAAT INI: {current_step.get('name', 'Unknown')}
   Deskripsi: {current_step.get('description', '-')}
   Progress Step: {current_step.get('index', 0) + 1} dari {current_step.get('total_steps', 1)}
   
📊 PROGRESS KESELURUHAN: {completion:.0f}% selesai

📝 DATA YANG SUDAH DIKUMPULKAN:
{collected_str}

❗ DATA YANG MASIH DIPERLUKAN DI TAHAP INI:
{missing_str}

🔄 PHASE: {phase}
"""
        return context_prompt
    
    async def process_contextual_message(
        self,
        user_message: str,
        session_context: Dict[str, Any],
        available_fields: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Process message dengan full context - determine intent & extract data
        """
        
        context_prompt = self._build_session_context_prompt(session_context)
        
        # Build field description
        field_desc = []
        for f in available_fields:
            desc = f"- {f['id']}: {f['label']} (type: {f['type']})"
            if f.get('examples'):
                examples_str = ', '.join(str(e) for e in f['examples'][:2])
                desc += f" | contoh: {examples_str}"
            if f.get('options'):
                opts = [o.get('value', '') for o in f['options'][:3]]
                desc += f" | pilihan: {', '.join(opts)}"
            field_desc.append(desc)
        
        field_desc_str = "\n".join(field_desc) if field_desc else "(tidak ada field di tahap ini)"
        
        system_prompt = f"""Kamu adalah AI asisten pendaftaran sekolah Al-Azhar yang CERDAS dan MEMAHAMI KONTEKS.

{context_prompt}

FIELD YANG TERSEDIA DI TAHAP INI:
{field_desc_str}

TUGASMU:
1. PAHAMI intent user:
   - "data_input": User memberikan data (nama, tanggal lahir, alamat, nomor telepon, dll)
   - "question": User bertanya tentang proses/persyaratan/informasi
   - "command": User memberi perintah (lanjut, kembali, summary, help, konfirmasi, ulang)
   - "clarification": User butuh penjelasan atau bingung (gimana, maksudnya, ga ngerti)
   - "greeting": User menyapa (halo, hai, pagi, siang, malam)

2. Jika intent = "data_input":
   - Extract field values dari pesan
   - Nilai HARUS murni tanpa label
   - Match dengan field yang tersedia di tahap ini
   
3. Jika intent = "question" atau "clarification":
   - Berikan suggested_response yang helpful sesuai konteks tahap saat ini
   - Sebutkan data apa yang diperlukan berikutnya

4. Jika intent = "command":
   - Identifikasi command: lanjut/next, kembali/back, summary, help, konfirmasi, ulang/reset

CONTOH INTENT DETECTION:
- "nama saya Ahmad" → data_input, extract nama_lengkap
- "saya Ahmad, lahir di Jakarta" → data_input, extract nama + tempat_lahir
- "apa saja persyaratan?" → question
- "lanjut ke tahap berikutnya" → command
- "maksudnya gimana?" → clarification
- "halo" → greeting
- "bantuan" → command (help)

RESPONSE FORMAT (JSON ONLY):
{{
    "intent": "data_input|question|command|clarification|greeting",
    "extracted_fields": {{}},
    "suggested_response": "...",
    "confidence": 0.0-1.0,
    "detected_command": null,
    "next_field_hint": "..."
}}

PENTING:
- Untuk intent "data_input", extracted_fields WAJIB diisi jika ada data
- Untuk intent lain, extracted_fields bisa kosong {{}}
- suggested_response WAJIB diisi untuk question/clarification/greeting
- detected_command diisi untuk intent "command" (nilai: lanjut/kembali/summary/help/konfirmasi/ulang)
"""

        user_prompt = f'PESAN USER: "{user_message}"\n\nAnalisis dan respond dalam JSON:'
        
        try:
            response = await self.generate(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=800,
                json_mode=True
            )
            
            result = json.loads(response)
            
            # Post-process extracted fields
            if result.get("extracted_fields"):
                cleaned = {}
                for key, value in result["extracted_fields"].items():
                    if isinstance(value, str):
                        cleaned_value = re.sub(r'^[^:]+:\s*', '', value).strip()
                        cleaned[key] = cleaned_value if cleaned_value else value
                    else:
                        cleaned[key] = value
                result["extracted_fields"] = cleaned
            
            return result
            
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            return {
                "intent": "clarification",
                "extracted_fields": {},
                "suggested_response": f"Saat ini Anda berada di tahap {session_context.get('current_step', {}).get('name', 'pendaftaran')}. Silakan berikan data yang diminta atau ketik 'help' untuk bantuan.",
                "confidence": 0.3
            }
        except Exception as e:
            print(f"Process contextual error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "intent": "clarification",
                "extracted_fields": {},
                "suggested_response": f"Saat ini Anda berada di tahap {session_context.get('current_step', {}).get('name', 'pendaftaran')}. Silakan berikan data yang diminta atau ketik 'help' untuk bantuan.",
                "confidence": 0.5
            }


# =============================================================================
# ANTHROPIC CLIENT
# =============================================================================

class AnthropicClient(BaseLLMClient):
    """Anthropic Claude client dengan contextual understanding"""
    
    def __init__(self):
        from anthropic import AsyncAnthropic
        config = settings.llm.get("anthropic", {})
        self.client = AsyncAnthropic(api_key=config.get("api_key"))
        self.model = config.get("model", "claude-3-sonnet-20240229")
        self.vision_model = config.get("vision_model", "claude-3-sonnet-20240229")
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
    
    async def analyze_image(self, image_base64: str, media_type: str, 
                           prompt: str) -> Optional[str]:
        """Analyze image using Anthropic Claude Vision API"""
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
                        {"type": "text", "text": prompt}
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
    
    async def explain_examples(self, field: Dict[str, Any], examples: List[str],
                               user_message: str, context: str) -> str:
        """Explain examples for a field"""
        examples_text = "\n".join([f"- {e}" for e in examples[:10]])
        system_prompt = (
            f"User meminta contoh untuk field '{field.get('label')}'. "
            "Jawab singkat dan ramah dalam bahasa Indonesia, tampilkan contoh sebagai daftar."
        )
        try:
            response = await self.generate(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Contoh:\n{examples_text}"}
                ],
                temperature=0.3,
                max_tokens=200,
            )
            return response.strip()
        except Exception as e:
            print(f"Anthropic explain_examples error: {e}")
            return "Contoh:\n" + ("\n".join([f"• {e}" for e in examples[:5]]) if examples else "Tidak ada contoh.")
    
    async def extract_fields(self, user_message: str, context: str,
                            available_fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract field values from user message"""
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
3. Contoh salah: {{"nama_lengkap": "Nama Lengkap: Ahmad"}}
4. Return {{}} jika tidak ada data"""
        
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
    
    # =========================================================================
    # NEW: Contextual Understanding Methods
    # =========================================================================
    
    def _build_session_context_prompt(self, session_context: Dict[str, Any]) -> str:
        """Build detailed session context for LLM"""
        
        current_step = session_context.get("current_step", {})
        collected_data = session_context.get("collected_data", {})
        missing_fields = session_context.get("missing_fields", [])
        completion = session_context.get("completion_percentage", 0)
        phase = session_context.get("phase", "collecting")
        
        collected_str = ""
        if collected_data:
            items = [f"  - {k}: {v}" for k, v in collected_data.items() if not k.startswith("_")]
            collected_str = "\n".join(items) if items else "  (belum ada data)"
        else:
            collected_str = "  (belum ada data)"
        
        missing_str = ""
        if missing_fields:
            missing_str = "\n".join([f"  - {f.get('label', f.get('id'))}" for f in missing_fields[:5]])
        else:
            missing_str = "  (semua data wajib sudah lengkap)"
        
        return f"""
=== KONTEKS SESI PENDAFTARAN ===

📍 TAHAP: {current_step.get('name', 'Unknown')}
   Deskripsi: {current_step.get('description', '-')}
   
📊 PROGRESS: {completion:.0f}%

📝 DATA TERKUMPUL:
{collected_str}

❗ DATA DIPERLUKAN:
{missing_str}

🔄 PHASE: {phase}
"""
    
    async def process_contextual_message(
        self,
        user_message: str,
        session_context: Dict[str, Any],
        available_fields: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Process message dengan full context"""
        
        context_prompt = self._build_session_context_prompt(session_context)
        
        field_desc = []
        for f in available_fields:
            desc = f"- {f['id']}: {f['label']} (type: {f['type']})"
            if f.get('examples'):
                desc += f" | contoh: {', '.join(str(e) for e in f['examples'][:2])}"
            field_desc.append(desc)
        
        field_desc_str = "\n".join(field_desc) if field_desc else "(tidak ada field)"
        
        system_prompt = f"""Kamu AI asisten pendaftaran sekolah Al-Azhar.

{context_prompt}

FIELD DI TAHAP INI:
{field_desc_str}

INTENT:
- "data_input": User beri data
- "question": User bertanya
- "command": User perintah (lanjut/kembali/summary/help/konfirmasi/ulang)
- "clarification": User bingung
- "greeting": User sapa

RESPOND JSON:
{{"intent": "...", "extracted_fields": {{}}, "suggested_response": "...", "confidence": 0.0-1.0, "detected_command": null}}"""

        try:
            response = await self.generate(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f'PESAN: "{user_message}"'}
                ],
                temperature=0.2,
                max_tokens=600,
                json_mode=True
            )
            
            result = json.loads(response)
            
            if result.get("extracted_fields"):
                cleaned = {}
                for key, value in result["extracted_fields"].items():
                    if isinstance(value, str):
                        cleaned[key] = re.sub(r'^[^:]+:\s*', '', value).strip() or value
                    else:
                        cleaned[key] = value
                result["extracted_fields"] = cleaned
            
            return result
            
        except Exception as e:
            print(f"Anthropic contextual error: {e}")
            return {
                "intent": "clarification",
                "extracted_fields": {},
                "suggested_response": f"Anda di tahap {session_context.get('current_step', {}).get('name', 'pendaftaran')}. Ketik 'help' untuk bantuan.",
                "confidence": 0.5
            }


# =============================================================================
# MOCK CLIENT (for testing)
# =============================================================================

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
        return f"Contoh {field.get('label')}:\n" + "\n".join([f"• {e}" for e in examples[:5]])
    
    async def analyze_image(self, image_base64: str, media_type: str, 
                           prompt: str) -> Optional[str]:
        return '{"type": "unknown", "confidence": 0.0, "reason": "Mock client"}'
    
    async def extract_fields(self, user_message: str, context: str,
                            available_fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        result = {}
        message_lower = user_message.lower()
        
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
    
    async def process_contextual_message(
        self,
        user_message: str,
        session_context: Dict[str, Any],
        available_fields: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Mock contextual processing"""
        msg_lower = user_message.lower().strip()
        
        # Simple intent detection
        if msg_lower in ["halo", "hai", "hi", "hello", "pagi", "siang", "sore", "malam"]:
            return {
                "intent": "greeting",
                "extracted_fields": {},
                "suggested_response": f"Halo! Anda di tahap {session_context.get('current_step', {}).get('name', 'pendaftaran')}.",
                "confidence": 0.9
            }
        
        if any(k in msg_lower for k in ["gimana", "maksud", "bingung", "ga ngerti", "tidak mengerti"]):
            return {
                "intent": "clarification",
                "extracted_fields": {},
                "suggested_response": "Silakan berikan data yang diminta atau ketik 'help'.",
                "confidence": 0.8
            }
        
        if any(k in msg_lower for k in ["apa saja", "persyaratan", "bagaimana", "caranya"]):
            return {
                "intent": "question",
                "extracted_fields": {},
                "suggested_response": f"Di tahap ini Anda perlu mengisi data yang diminta.",
                "confidence": 0.7
            }
        
        # Try to extract fields
        extracted = await self.extract_fields(user_message, "", available_fields)
        
        return {
            "intent": "data_input",
            "extracted_fields": extracted,
            "suggested_response": None,
            "confidence": 0.6 if extracted else 0.3
        }


# =============================================================================
# HYBRID CLIENT (Optional - use different providers for different tasks)
# =============================================================================

class HybridLLMClient(BaseLLMClient):
    """Hybrid client that can use different providers for different tasks"""
    
    def __init__(self):
        config = settings.llm
        self.text_provider = config.get("text_provider", settings.llm_provider)
        self.vision_provider = config.get("vision_provider", settings.llm_provider)
        self._text_client = None
        self._vision_client = None
    
    def _get_client(self, provider: str) -> BaseLLMClient:
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
    
    async def explain_examples(self, field: Dict[str, Any], examples: List[str],
                               user_message: str, context: str) -> str:
        return await self.text_client.explain_examples(field, examples, user_message, context)
    
    async def process_contextual_message(
        self,
        user_message: str,
        session_context: Dict[str, Any],
        available_fields: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        return await self.text_client.process_contextual_message(
            user_message, session_context, available_fields
        )


# =============================================================================
# FACTORY & SINGLETON
# =============================================================================

def get_llm_client() -> BaseLLMClient:
    """Get LLM client based on configuration"""
    provider = settings.llm_provider
    
    if settings.llm.get("hybrid_mode", False):
        return HybridLLMClient()
    
    if provider == "openai":
        return OpenAIClient()
    elif provider == "anthropic":
        return AnthropicClient()
    elif provider == "mock":
        return MockLLMClient()
    else:
        print(f"Unknown LLM provider: {provider}, using OpenAI as default")
        return OpenAIClient()


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