"""
Chat Handler - Enhanced with Contextual Understanding + EDIT IMPROVEMENTS
==========================================================================
Features:
- Full session context awareness
- Intent detection (greeting, question, data_input, command, clarification)
- Helpful responses instead of "tidak memahami"
- Smart document classification
- IMPROVED: Enhanced edit request handling with field aliases

CARA PAKAI:
- Replace file chat_handler.py existing dengan file ini
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import re
import json

from transaksional.app.form_manager import get_form_manager, DynamicFormManager, FieldConfig
from transaksional.app.session_state import SessionState, SessionManager, get_session_manager, SessionStatus
from transaksional.app.llm_client import get_llm, BaseLLMClient


# =============================================================================
# ENUMS & DATACLASSES
# =============================================================================

class ConversationPhase(str, Enum):
    COLLECTING = "collecting"
    UPLOADING_DOCUMENTS = "uploading_documents"
    PRE_CONFIRM = "pre_confirm"
    AWAITING_CONFIRM = "awaiting_confirm"
    AWAITING_RESET = "awaiting_reset"
    CONFIRMED = "confirmed"
    ASK_NEW_REGISTRATION = "ask_new"


@dataclass
class ChatResult:
    response: str
    session_id: str
    current_step: str
    phase: str
    completion_percentage: float
    fields_updated: List[str] = field(default_factory=list)
    fields_created: List[str] = field(default_factory=list)
    validation_errors: Dict[str, str] = field(default_factory=dict)
    can_advance: bool = False
    can_confirm: bool = False
    can_go_back: bool = False
    is_complete: bool = False
    registration_number: Optional[str] = None
    registration_status: Optional[str] = None
    step_info: Dict[str, Any] = None
    documents_status: Dict[str, Any] = None
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


# =============================================================================
# FIELD ALIASES - Keyword mapping untuk edit detection
# =============================================================================

FIELD_ALIASES = {
    # === Data Siswa ===
    "nama": "nama_lengkap",
    "nama lengkap": "nama_lengkap",
    "nama siswa": "nama_lengkap",
    "nama anak": "nama_lengkap",
    "nama murid": "nama_lengkap",
    "namanya": "nama_lengkap",
    
    "panggilan": "nama_panggilan",
    "nama panggilan": "nama_panggilan",
    "dipanggil": "nama_panggilan",
    
    "kelamin": "jenis_kelamin",
    "jenis kelamin": "jenis_kelamin",
    "gender": "jenis_kelamin",
    
    "tempat lahir": "tempat_lahir",
    "kota lahir": "tempat_lahir",
    "lahir di": "tempat_lahir",
    "ttl": "tempat_lahir",
    
    "tanggal lahir": "tanggal_lahir",
    "tgl lahir": "tanggal_lahir",
    "dob": "tanggal_lahir",
    
    "nik": "nik",
    "nomor induk": "nik",
    
    "agama": "agama",
    
    "anak ke": "anak_ke",
    "jumlah saudara": "jumlah_saudara",
    "saudara": "jumlah_saudara",
    
    # === Alamat ===
    "alamat": "alamat_lengkap",
    "alamat lengkap": "alamat_lengkap",
    "alamat rumah": "alamat_lengkap",
    "tempat tinggal": "alamat_lengkap",
    
    "rt": "rt",
    "rw": "rw",
    "kelurahan": "kelurahan",
    "desa": "kelurahan",
    "kecamatan": "kecamatan",
    "kota": "kabupaten_kota",
    "kabupaten": "kabupaten_kota",
    "provinsi": "provinsi",
    "kode pos": "kode_pos",
    "pos": "kode_pos",
    
    # === Kontak ===
    "telepon": "nomor_telepon",
    "telp": "nomor_telepon",
    "no telp": "nomor_telepon",
    "nomor telepon": "nomor_telepon",
    
    "hp": "nomor_hp",
    "handphone": "nomor_hp",
    "no hp": "nomor_hp",
    "nomor hp": "nomor_hp",
    "whatsapp": "nomor_hp",
    "wa": "nomor_hp",
    "nomer hp": "nomor_hp",
    
    "email": "email",
    "e-mail": "email",
    
    # === Data Orang Tua - Ayah ===
    "nama ayah": "nama_ayah",
    "ayah": "nama_ayah",
    "bapak": "nama_ayah",
    
    "pekerjaan ayah": "pekerjaan_ayah",
    "kerja ayah": "pekerjaan_ayah",
    "kerjaan ayah": "pekerjaan_ayah",
    
    "pendidikan ayah": "pendidikan_ayah",
    
    "penghasilan ayah": "penghasilan_ayah",
    "gaji ayah": "penghasilan_ayah",
    
    "hp ayah": "nomor_hp_ayah",
    "telp ayah": "nomor_hp_ayah",
    "no hp ayah": "nomor_hp_ayah",
    "wa ayah": "nomor_hp_ayah",
    
    # === Data Orang Tua - Ibu ===
    "nama ibu": "nama_ibu",
    "ibu": "nama_ibu",
    "mamah": "nama_ibu",
    "mama": "nama_ibu",
    
    "pekerjaan ibu": "pekerjaan_ibu",
    "kerja ibu": "pekerjaan_ibu",
    "kerjaan ibu": "pekerjaan_ibu",
    
    "pendidikan ibu": "pendidikan_ibu",
    
    "penghasilan ibu": "penghasilan_ibu",
    "gaji ibu": "penghasilan_ibu",
    
    "hp ibu": "nomor_hp_ibu",
    "telp ibu": "nomor_hp_ibu",
    "no hp ibu": "nomor_hp_ibu",
    "wa ibu": "nomor_hp_ibu",
    
    # === Pilihan Sekolah ===
    "jenjang": "jenjang_pendidikan",
    "tingkat": "jenjang_pendidikan",
    "level": "jenjang_pendidikan",
    "jenjangnya": "jenjang_pendidikan",
    "tk": "jenjang_pendidikan",
    "sd": "jenjang_pendidikan",
    "smp": "jenjang_pendidikan",
    "sma": "jenjang_pendidikan",
    
    "sekolah": "pilihan_sekolah",
    "pilihan sekolah": "pilihan_sekolah",
    "sekolahnya": "pilihan_sekolah",
    "cabang": "pilihan_sekolah",
    "unit": "pilihan_sekolah",
    
    "program": "program_khusus",
    "program khusus": "program_khusus",
    "jurusan": "program_khusus",
    
    "tahun ajaran": "tahun_ajaran",
    "ta": "tahun_ajaran",
    "angkatan": "tahun_ajaran",
    
    # === Riwayat Pendidikan ===
    "asal sekolah": "asal_sekolah",
    "sekolah asal": "asal_sekolah",
    "sekolah sebelumnya": "asal_sekolah",
    
    "kelas terakhir": "kelas_terakhir",
    "kelas": "kelas_terakhir",
    
    "nilai rata-rata": "nilai_rata_rata",
    "nilai": "nilai_rata_rata",
    "rata-rata": "nilai_rata_rata",
    
    # === Kesehatan ===
    "tinggi badan": "tinggi_badan",
    "tinggi": "tinggi_badan",
    "tb": "tinggi_badan",
    
    "berat badan": "berat_badan",
    "berat": "berat_badan",
    "bb": "berat_badan",
    
    "golongan darah": "golongan_darah",
    "gol darah": "golongan_darah",
    "darah": "golongan_darah",
    
    "riwayat penyakit": "riwayat_penyakit",
    "penyakit": "riwayat_penyakit",
    
    "alergi": "alergi",
}


# =============================================================================
# HELPER FUNCTIONS FOR EDIT DETECTION
# =============================================================================

def detect_target_field_from_message(
    message: str, 
    all_fields: List,  # List of FieldConfig
    collected_data: Dict[str, Any]
) -> Optional[str]:
    """
    Deteksi field mana yang ingin diubah user berdasarkan keyword.
    Return field_id atau None jika tidak terdeteksi.
    """
    message_lower = message.lower()
    
    # 1. Check field label mention (paling spesifik, prioritas tinggi)
    for field in all_fields:
        label = (field.label or '').lower()
        if label and len(label) > 2 and label in message_lower:
            return field.id
    
    # 2. Check direct field_id mention (with spaces instead of underscore)
    for field in all_fields:
        field_id = field.id
        if field_id.replace("_", " ") in message_lower:
            return field_id
    
    # 3. Check aliases (sorted by length desc untuk match yang lebih spesifik dulu)
    sorted_aliases = sorted(FIELD_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)
    for alias, field_id in sorted_aliases:
        if alias in message_lower:
            if any(f.id == field_id for f in all_fields):
                return field_id
    
    # 4. Check extract_keywords dari field config
    for field in all_fields:
        for kw in (field.extract_keywords or []):
            if kw.lower() in message_lower:
                return field.id
    
    return None


def extract_new_value_from_edit_message(message: str) -> Optional[str]:
    """
    Extract nilai baru dari pesan edit.
    Return nilai atau None jika tidak terdeteksi.
    """
    patterns = [
        # "ubah X menjadi/jadi/ke Y"
        r'(?:ubah|ganti|koreksi|perbaiki|edit|update|ralat)\s+[\w\s]+?\s+(?:menjadi|jadi|ke)\s+(.+?)(?:\s*[,.]|$)',
        # "X yang benar adalah Y" atau "yang benar X"
        r'(?:yang\s+benar(?:\s+adalah)?|seharusnya|harusnya)\s+(.+?)(?:\s*[,.]|$)',
        # "bukan X tapi Y"
        r'bukan\s+[\w\s]+?\s+(?:tapi|tetapi|melainkan)\s+(.+?)(?:\s*[,.]|$)',
        # "X: Y" atau "X = Y"  
        r'[\w\s]+?[:\=]\s*(.+?)(?:\s*[,.]|$)',
        # Simple: setelah keyword edit, ambil sisanya
        r'(?:ubah|ganti|koreksi|perbaiki)\s+\w+\s+(.+?)(?:\s*[,.]|$)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            # Clean up common suffixes
            value = re.sub(r'\s+(ya|dong|gan|pak|bu|mas|mbak|nih|deh)$', '', value, flags=re.IGNORECASE)
            if value and len(value) > 0:
                return value
    
    return None


# =============================================================================
# HELPER FUNCTION: Build Session Context
# =============================================================================

def build_session_context(session: SessionState, form_manager: DynamicFormManager) -> Dict[str, Any]:
    """
    Build comprehensive session context untuk dikirim ke LLM.
    Ini adalah kunci agar LLM memahami konteks pendaftaran!
    """
    current_step_id = session.current_step
    current_step_obj = form_manager.get_step(current_step_id)
    
    # Get fields for current step
    current_fields = form_manager.get_fields_for_step(current_step_id)
    missing_fields = form_manager.get_missing_mandatory_fields(current_step_id, session.raw_data)
    
    # Calculate completion
    completion = form_manager.calculate_completion(session.raw_data)
    
    # Get recent conversation for context
    recent_messages = session.get_recent_messages(5)
    
    # Get all steps for progress visualization
    all_steps = form_manager.get_steps()
    current_step_index = form_manager.get_step_index(current_step_id)
    
    return {
        "session_id": session.session_id,
        "current_step": {
            "id": current_step_id,
            "name": current_step_obj.name if current_step_obj else "",
            "description": current_step_obj.description if current_step_obj else "",
            "icon": current_step_obj.raw_config.get("icon", "") if current_step_obj else "",
            "index": current_step_index,
            "total_steps": len(all_steps)
        },
        "collected_data": {
            k: v for k, v in session.raw_data.items() 
            if not k.startswith("_")  # Exclude internal fields
        },
        "missing_fields": [
            {
                "id": f.id,
                "label": f.label,
                "type": f.type,
                "examples": f.examples[:2] if f.examples else [],
                "tips": f.tips,
                "is_mandatory": f.is_mandatory
            }
            for f in missing_fields
        ],
        "current_fields": [
            {
                "id": f.id,
                "label": f.label,
                "type": f.type,
                "is_filled": session.raw_data.get(f.id) is not None
            }
            for f in current_fields
        ],
        "completion_percentage": completion,
        "phase": session.raw_data.get("_phase", "collecting"),
        "recent_messages": recent_messages,
        "validation_errors": session.validation_errors,
        "can_advance": form_manager.can_advance_from_step(current_step_id, session.raw_data),
        "registration_number": session.registration_number
    }


# =============================================================================
# CHAT HANDLER CLASS
# =============================================================================

class ChatHandler:
    def __init__(self):
        self.form_manager: DynamicFormManager = get_form_manager()
        self.session_manager: SessionManager = get_session_manager()
        self.llm: BaseLLMClient = get_llm()
    
    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================
    
    async def process_message(self, session_id: str, user_message: str, 
                              file_path: str = None, file_info: Dict = None, 
                              user_id: str = None) -> ChatResult:
        """
        Process chat message with optional file upload.
        """
        session = self._get_or_create_session(session_id)
        session.add_message("user", user_message)
        
        current_phase = session.raw_data.get("_phase", ConversationPhase.COLLECTING.value)
        print(f"Processing message in phase: {current_phase}")
        
        # Check for registration number (status check)
        reg_number = self._extract_registration_number(user_message)
        
        if reg_number:
            result = await self._handle_check_status(session, reg_number)
        elif current_phase == ConversationPhase.UPLOADING_DOCUMENTS.value:
            result = await self._handle_document_phase(session, user_message, file_path, file_info)
        elif current_phase == ConversationPhase.AWAITING_CONFIRM.value:
            result = await self._handle_confirmation_response(session, user_message, user_id)
        elif current_phase == ConversationPhase.AWAITING_RESET.value:
            result = await self._handle_reset_response(session, user_message)
        elif current_phase == ConversationPhase.ASK_NEW_REGISTRATION.value:
            result = await self._handle_post_confirmation(session, user_message)
        elif current_phase == ConversationPhase.CONFIRMED.value:
            result = await self._handle_post_confirmation(session, user_message)
        else:
            # Check if edit request
            if await self._is_edit_request(user_message, session):
                result = await self._handle_edit_request(session, user_message)
            else:
                # Check for command first
                command = self.form_manager.detect_command(user_message)
                print(f"Detected command: {command}")
                if command:
                    result = await self._handle_command(session, command, user_message)
                else:
                    # Use enhanced data input handler with contextual understanding
                    result = await self._handle_data_input(session, user_message)
        
        self.session_manager.save_session(session)
        session.add_message("assistant", result.response)
        return result
    
    # =========================================================================
    # SESSION MANAGEMENT
    # =========================================================================
    
    def _get_or_create_session(self, session_id: str) -> SessionState:
        session = self.session_manager.get_session(session_id)
        if not session:
            first_step = self.form_manager.get_first_step()
            session = self.session_manager.create_session(initial_step=first_step.id if first_step else "")
            session.session_id = session_id
            session.raw_data["_phase"] = ConversationPhase.COLLECTING.value
            self.session_manager.save_session(session)
        return session
    
    def _extract_registration_number(self, message: str) -> Optional[str]:
        pattern = r'AZHAR-\d{4}-[A-Z]{2,3}-[A-Z0-9]{8}'
        match = re.search(pattern, message.upper())
        return match.group(0) if match else None

    async def _is_edit_request(self, message: str, session: SessionState) -> bool:
        edit_keywords = ["ubah", "ganti", "koreksi", "perbaiki", "salah", "edit", "update", 
                        "ralat", "bukan", "harusnya", "seharusnya", "yang benar"]
        message_lower = message.lower()
        return any(kw in message_lower for kw in edit_keywords)
    
    # =========================================================================
    # ENHANCED DATA INPUT HANDLER - WITH CONTEXTUAL UNDERSTANDING
    # =========================================================================
    
    async def _handle_data_input(self, session: SessionState, user_message: str) -> ChatResult:
        """
        ENHANCED: Handle data input dengan contextual understanding.
        Mendeteksi intent dan memberikan response yang sesuai konteks.
        """
        current_step = session.current_step
        fields = self.form_manager.get_fields_for_step(current_step)

        # =====================================================
        # STEP 1: Deteksi request contoh (existing logic)
        # =====================================================
        ask_examples_keywords = [
            "contoh", "contohnya", "sebutkan contoh", "apa contohnya", "ada contoh"
        ]
        if any(k in user_message.lower() for k in ask_examples_keywords):
            return await self._handle_ask_examples(session, user_message)

        # =====================================================
        # STEP 2: Build comprehensive session context
        # =====================================================
        session_context = build_session_context(session, self.form_manager)
        
        fields_dict = [
            {
                "id": f.id,
                "label": f.label,
                "type": f.type,
                "examples": f.examples,
                "options": f.options,
                "extract_keywords": f.extract_keywords,
                "is_mandatory": f.is_mandatory
            }
            for f in fields
        ]
        
        # =====================================================
        # STEP 3: Use contextual processing with LLM
        # =====================================================
        try:
            if hasattr(self.llm, 'process_contextual_message'):
                result = await self.llm.process_contextual_message(
                    user_message=user_message,
                    session_context=session_context,
                    available_fields=fields_dict
                )
            else:
                # Fallback to existing extraction
                result = {
                    "intent": "data_input",
                    "extracted_fields": await self._extract_fields_with_llm(user_message, fields, session),
                    "suggested_response": None,
                    "confidence": 0.5
                }
        except Exception as e:
            print(f"Contextual processing error: {e}")
            import traceback
            traceback.print_exc()
            result = {
                "intent": "data_input",
                "extracted_fields": {},
                "suggested_response": None,
                "confidence": 0.0
            }
        
        intent = result.get("intent", "data_input")
        extracted = result.get("extracted_fields", {})
        suggested_response = result.get("suggested_response", "")
        confidence = result.get("confidence", 0.5)
        detected_command = result.get("detected_command")
        
        print(f"Intent: {intent}, Confidence: {confidence}, Extracted: {extracted}, Command: {detected_command}")
        
        # =====================================================
        # STEP 4: Handle based on intent
        # =====================================================
        
        # --- GREETING ---
        if intent == "greeting":
            return self._handle_greeting(session, session_context)
        
        # --- QUESTION ---
        if intent == "question":
            if suggested_response:
                response = suggested_response
            else:
                response = self._generate_helpful_response(session_context, "question")
            return self._build_result(session, response)
        
        # --- CLARIFICATION ---
        if intent == "clarification":
            if suggested_response:
                response = suggested_response
            else:
                response = self._generate_helpful_response(session_context, "clarification")
            return self._build_result(session, response)
        
        # --- COMMAND (detected by LLM) ---
        if intent == "command" and detected_command:
            command_map = {
                "lanjut": "advance",
                "next": "advance",
                "kembali": "back",
                "back": "back",
                "summary": "summary",
                "ringkasan": "summary",
                "help": "help",
                "bantuan": "help",
                "konfirmasi": "confirm",
                "ulang": "reset",
                "reset": "reset"
            }
            mapped_command = command_map.get(detected_command.lower())
            if mapped_command:
                return await self._handle_command(session, mapped_command, user_message)
        
        # Also try existing command detection as fallback
        command = self.form_manager.detect_command(user_message)
        if command:
            return await self._handle_command(session, command, user_message)
        
        # --- DATA INPUT ---
        extraction_result = extracted
        
        # Fallback to LLM extraction if no results
        if not extraction_result:
            print("No extraction from contextual, trying direct extraction...")
            extraction_result = await self._extract_fields_with_llm(user_message, fields, session)
        
        # Fallback to simple extraction
        if not extraction_result:
            print("No LLM extraction, trying simple extraction...")
            extraction_result = self.form_manager.extract_fields_simple(user_message, fields)
        
        # Process extracted fields
        confirmed_values = []
        validation_errors = {}
        
        for field_id, value in extraction_result.items():
            field = self.form_manager.get_field(field_id)
            if not field:
                continue
            
            is_valid, error_msg, cleaned_value = self.form_manager.validate_field(field_id, value)
            
            if is_valid:
                action = session.set_field(field_id, cleaned_value, field.label)
                session.clear_validation_error(field_id)
                confirmed_values.append((field, cleaned_value, action))
            else:
                session.set_validation_error(field_id, error_msg)
                validation_errors[field_id] = error_msg
        
        print(f"Confirmed values: {confirmed_values}")
        print(f"Validation errors: {validation_errors}")
        
        # =====================================================
        # STEP 5: Build response or handle unknown input
        # =====================================================
        if not confirmed_values and not validation_errors:
            # No data extracted - provide helpful response instead of "tidak memahami"
            return self._handle_unknown_input(session, session_context, user_message)
        
        response = self._build_input_response(session, confirmed_values, validation_errors, current_step)
        
        return self._build_result(
            session, response,
            fields_updated=[f.id for f, _, a in confirmed_values if a == "update"],
            fields_created=[f.id for f, _, a in confirmed_values if a == "create"],
            validation_errors=validation_errors
        )
    
    # =========================================================================
    # HELPER METHODS FOR CONTEXTUAL RESPONSES
    # =========================================================================
    
    def _handle_greeting(self, session: SessionState, session_context: Dict) -> ChatResult:
        """Handle greeting with context-aware response"""
        current_step = session_context.get("current_step", {})
        missing_fields = session_context.get("missing_fields", [])
        completion = session_context.get("completion_percentage", 0)
        
        response_parts = []
        response_parts.append(f"Halo! 👋 Selamat datang di pendaftaran Al-Azhar.\n\n")
        response_parts.append(f"📍 Anda sedang di tahap **{current_step.get('name', 'pendaftaran')}**")
        
        if current_step.get("description"):
            response_parts.append(f"\n   {current_step['description']}")
        
        response_parts.append(f"\n\n📊 Progress: **{completion:.0f}%** selesai")
        
        if missing_fields:
            next_field = missing_fields[0]
            response_parts.append(f"\n\n▶️ Selanjutnya, mohon berikan **{next_field.get('label')}**.")
            if next_field.get('examples'):
                response_parts.append(f"\n\n💡 Contoh: {next_field['examples'][0]}")
        else:
            response_parts.append(f"\n\n✅ Semua data di tahap ini sudah lengkap!")
            response_parts.append(f"\nKetik **'lanjut'** untuk melanjutkan ke tahap berikutnya.")
        
        return self._build_result(session, "".join(response_parts))
    
    def _generate_helpful_response(self, session_context: Dict, intent: str) -> str:
        """Generate helpful response based on context and intent"""
        current_step = session_context.get("current_step", {})
        missing_fields = session_context.get("missing_fields", [])
        completion = session_context.get("completion_percentage", 0)
        collected_data = session_context.get("collected_data", {})
        
        response_parts = []
        
        if intent == "question":
            response_parts.append(f"📍 Anda sedang di tahap **{current_step.get('name', 'pendaftaran')}**.\n")
            
            if current_step.get("description"):
                response_parts.append(f"{current_step['description']}\n")
            
            response_parts.append(f"\n📊 Progress: **{completion:.0f}%** selesai")
            
            # Show collected data
            if collected_data:
                response_parts.append(f"\n\n✅ **Data yang sudah diisi:**")
                for k, v in list(collected_data.items())[:5]:
                    response_parts.append(f"\n  • {k}: {v}")
            
            # Show missing fields
            if missing_fields:
                response_parts.append(f"\n\n❗ **Data yang masih diperlukan:**")
                for f in missing_fields[:4]:
                    example_text = f" _(contoh: {f['examples'][0]})_" if f.get('examples') else ""
                    response_parts.append(f"\n  • {f.get('label')}{example_text}")
            
            response_parts.append(f"\n\n💡 Ketik **'help'** untuk panduan lengkap.")
        
        elif intent == "clarification":
            response_parts.append("Tidak masalah, saya jelaskan ya! 😊\n\n")
            
            if missing_fields:
                next_field = missing_fields[0]
                response_parts.append(f"Saat ini saya membutuhkan **{next_field.get('label')}**.\n")
                
                if next_field.get('tips'):
                    response_parts.append(f"\n💡 **Tips:** {next_field['tips']}\n")
                
                if next_field.get('examples'):
                    response_parts.append(f"\n📝 **Contoh cara mengisi:**")
                    for ex in next_field['examples'][:3]:
                        response_parts.append(f"\n  • \"{ex}\"")
            else:
                response_parts.append("Semua data di tahap ini sudah lengkap! 🎉\n")
                response_parts.append("\nKetik **'lanjut'** untuk ke tahap berikutnya.")
            
            response_parts.append(f"\n\n📌 Anda bisa mengetik **'help'** kapan saja untuk bantuan.")
        
        else:
            response_parts.append(f"📍 Anda sedang di tahap **{current_step.get('name', 'pendaftaran')}**.\n")
            response_parts.append("\nSilakan berikan data yang diminta atau ketik **'help'** untuk bantuan.")
        
        return "".join(response_parts)
    
    def _handle_unknown_input(self, session: SessionState, session_context: Dict, 
                              user_message: str) -> ChatResult:
        """Handle input yang tidak dikenali dengan response yang helpful"""
        current_step = session_context.get("current_step", {})
        missing_fields = session_context.get("missing_fields", [])
        
        response_parts = []
        
        # Don't just say "tidak memahami" - be helpful!
        response_parts.append("🤔 Hmm, saya belum bisa memproses input tersebut.\n\n")
        
        if missing_fields:
            next_field = missing_fields[0]
            response_parts.append(f"Saat ini saya membutuhkan **{next_field.get('label')}**.\n")
            
            # Provide examples
            if next_field.get('examples'):
                response_parts.append(f"\n📝 **Contoh cara mengisi:**")
                for ex in next_field['examples'][:2]:
                    response_parts.append(f"\n  • \"{ex}\"")
            
            # Provide tips
            if next_field.get('tips'):
                response_parts.append(f"\n\n💡 **Tips:** {next_field['tips']}")
            
            # Show field type hint
            field_type = next_field.get('type', 'text')
            if field_type == 'date':
                response_parts.append(f"\n\n📅 Format tanggal: DD/MM/YYYY (contoh: 15/05/2010)")
            elif field_type == 'phone':
                response_parts.append(f"\n\n📱 Format telepon: 08xxxxxxxxxx")
            elif field_type == 'email':
                response_parts.append(f"\n\n📧 Format email: nama@domain.com")
        else:
            response_parts.append(f"Anda sudah di tahap **{current_step.get('name')}** dan semua data sudah lengkap.\n")
            response_parts.append("\n✅ Ketik **'lanjut'** untuk melanjutkan atau **'summary'** untuk melihat ringkasan.")
        
        response_parts.append("\n\n📌 Ketik **'help'** untuk melihat panduan lengkap.")
        
        return self._build_result(session, "".join(response_parts))
    
    # =========================================================================
    # ASK EXAMPLES HANDLER
    # =========================================================================
    
    async def _handle_ask_examples(self, session: SessionState, user_message: str) -> ChatResult:
        """Handle request for examples"""
        current_step = session.current_step
        fields = self.form_manager.get_fields_for_step(current_step)

        message_lower = user_message.lower()
        
        # Find field that user mentioned
        matched_field = None
        for f in fields:
            if f.examples:
                label_lower = (f.label or "").lower()
                if label_lower and label_lower in message_lower:
                    matched_field = f
                    break
                if f.id and f.id.lower() in message_lower:
                    matched_field = f
                    break

        # If no match but only one field has examples, use that
        fields_with_examples = [f for f in fields if f.examples]
        if not matched_field:
            if len(fields_with_examples) == 1:
                matched_field = fields_with_examples[0]
            elif len(fields_with_examples) > 1:
                lines = ["📝 Ada beberapa field yang memiliki contoh:\n"]
                for f in fields_with_examples[:6]:
                    lines.append(f"• **{f.label}** - ketik 'contoh {f.label.lower()}'")
                return self._build_result(session, "\n".join(lines))

        if not matched_field:
            return self._build_result(session, "Maaf, saya tidak menemukan contoh untuk field ini di tahap saat ini.\n\nKetik **'help'** untuk bantuan.")

        # Use LLM to explain examples
        field_dict = {
            "id": matched_field.id,
            "label": matched_field.label,
            "type": matched_field.type
        }
        recent = session.get_recent_messages(8)
        context = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
        
        try:
            explanation = await self.llm.explain_examples(field_dict, matched_field.examples, user_message, context)
        except Exception as e:
            print(f"LLM explain_examples error: {e}")
            explanation = f"📝 **Contoh {matched_field.label}:**\n\n" + \
                          "\n".join([f"• {ex}" for ex in matched_field.examples[:5]])

        return self._build_result(session, explanation)
    
    # =========================================================================
    # EDIT REQUEST HANDLER - IMPROVED VERSION
    # =========================================================================
    
    async def _extract_edit_with_enhanced_prompt(self, user_message: str, 
                                                  fields_for_llm: List[Dict],
                                                  session: SessionState) -> Dict[str, Any]:
        """
        Extract fields dari perintah edit dengan prompt yang lebih spesifik.
        """
        # Build field description with aliases
        field_desc_parts = []
        for f in fields_for_llm:
            desc = f"- {f['id']}: {f['label']} (type: {f['type']})"
            if f.get('examples'):
                desc += f" | contoh: {f['examples'][0]}"
            
            # Find aliases for this field
            field_aliases = [alias for alias, fid in FIELD_ALIASES.items() if fid == f['id']]
            if field_aliases:
                desc += f" | keyword: {', '.join(field_aliases[:4])}"
            
            field_desc_parts.append(desc)
        
        field_desc_str = "\n".join(field_desc_parts)
        
        # Build existing data
        existing_items = []
        for field_id, value in session.raw_data.items():
            if not field_id.startswith("_") and value:
                label = field_id
                for f in fields_for_llm:
                    if f['id'] == field_id:
                        label = f.get('label', field_id)
                        break
                existing_items.append(f"  • {label} ({field_id}): {value}")
        
        existing_data_str = "\n".join(existing_items) if existing_items else "  (belum ada data)"
        
        system_prompt = f"""Kamu adalah AI untuk mengekstrak data dari perintah EDIT/UBAH user pada form pendaftaran sekolah.

📝 DATA YANG SUDAH TERKUMPUL (bisa diubah user):
{existing_data_str}

📋 SEMUA FIELD YANG TERSEDIA:
{field_desc_str}

TUGASMU:
1. Identifikasi field mana yang ingin diubah user berdasarkan keyword/alias
2. Extract nilai BARU yang diberikan user
3. Gunakan keyword/alias untuk mencocokkan dengan field_id yang benar
4. Return JSON dengan field_id dan nilai baru

CONTOH PERINTAH EDIT DAN HASIL:
- "ubah nama menjadi Ahmad Fauzi" → {{"nama_lengkap": "Ahmad Fauzi"}}
- "ganti hp jadi 08123456789" → {{"nomor_hp": "08123456789"}}  
- "alamat: Jl. Sudirman No. 10" → {{"alamat_lengkap": "Jl. Sudirman No. 10"}}
- "koreksi nama ayah Budi Santoso" → {{"nama_ayah": "Budi Santoso"}}
- "yang benar sekolahnya Al-Azhar Kelapa Gading" → {{"pilihan_sekolah": "Al-Azhar Kelapa Gading"}}
- "jenjangnya SD" → {{"jenjang_pendidikan": "SD"}}
- "ubah tanggal lahir ke 15/05/2010" → {{"tanggal_lahir": "15/05/2010"}}
- "pekerjaan ayah wiraswasta" → {{"pekerjaan_ayah": "Wiraswasta"}}

ATURAN PENTING:
1. Return HANYA JSON object, tanpa penjelasan
2. field_id harus PERSIS sama dengan yang tersedia di atas
3. Nilai harus MURNI tanpa label/prefix
4. Jika tidak jelas field mana, return {{}}
5. Perhatikan keyword: ubah, ganti, koreksi, perbaiki, ralat, yang benar, harusnya, seharusnya
6. Gunakan kolom "keyword" untuk mencocokkan istilah user dengan field_id"""

        user_prompt = f'PERINTAH EDIT USER: "{user_message}"\n\nExtract ke JSON:'
        
        try:
            response = await self.llm.generate(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                json_mode=True
            )
            
            result = json.loads(response)
            
            # Validate and clean
            cleaned = {}
            valid_field_ids = {f['id'] for f in fields_for_llm}
            
            for key, value in result.items():
                # Direct match
                if key in valid_field_ids:
                    if isinstance(value, str):
                        cleaned_value = re.sub(r'^[^:]+:\s*', '', value).strip()
                        cleaned[key] = cleaned_value if cleaned_value else value
                    else:
                        cleaned[key] = value
                else:
                    # Try alias match
                    actual_id = FIELD_ALIASES.get(key.lower())
                    if actual_id and actual_id in valid_field_ids:
                        if isinstance(value, str):
                            cleaned_value = re.sub(r'^[^:]+:\s*', '', value).strip()
                            cleaned[actual_id] = cleaned_value if cleaned_value else value
                        else:
                            cleaned[actual_id] = value
            
            return cleaned
            
        except json.JSONDecodeError as e:
            print(f"JSON decode error in edit extraction: {e}")
            return {}
        except Exception as e:
            print(f"Edit extraction error: {e}")
            return {}

    async def _handle_edit_request(self, session: SessionState, user_message: str) -> ChatResult:
        """
        IMPROVED: Handle edit/update request dengan pemahaman yang lebih baik.
        """
        all_fields = self.form_manager.get_all_fields()
        
        # Step 1: Try rule-based detection first (lebih cepat dan reliable)
        target_field_id = detect_target_field_from_message(user_message, all_fields, session.raw_data)
        
        extraction_result = {}
        
        # Step 2: If target field detected, try simple value extraction
        if target_field_id:
            new_value = extract_new_value_from_edit_message(user_message)
            if new_value:
                extraction_result[target_field_id] = new_value
                print(f"[EDIT] Rule-based extraction: {target_field_id} = {new_value}")
        
        # Step 3: If rule-based failed, use LLM with enhanced prompt
        if not extraction_result:
            # Prepare fields dict for LLM
            fields_for_llm = [
                {
                    "id": f.id,
                    "label": f.label,
                    "type": f.type,
                    "examples": f.examples or [],
                    "extract_keywords": f.extract_keywords or [],
                    "options": [{"value": o.value, "label": o.label} for o in (f.options or [])] if f.options else []
                }
                for f in all_fields
            ]
            
            extraction_result = await self._extract_edit_with_enhanced_prompt(
                user_message, 
                fields_for_llm, 
                session
            )
            print(f"[EDIT] LLM extraction: {extraction_result}")
        
        # Step 4: Fallback to regular extraction if still empty
        if not extraction_result:
            extraction_result = await self._extract_fields_with_llm(user_message, all_fields, session)
            print(f"[EDIT] Fallback extraction: {extraction_result}")
        
        # Step 5: Process results - jika tidak ada extraction
        if not extraction_result:
            response_parts = [
                "🤔 Maaf, saya tidak mengerti data mana yang ingin diubah.\n\n",
                "**Cara mengubah data:**\n",
                "• \"ubah nama menjadi Ahmad Fauzi\"\n",
                "• \"ganti alamat ke Jl. Sudirman No. 10\"\n", 
                "• \"koreksi tanggal lahir 15/05/2000\"\n",
                "• \"nama ayah yang benar Budi Santoso\"\n",
                "• \"hp: 081234567890\"\n",
                "• \"jenjang SD\"\n",
                "• \"sekolah Al-Azhar Kelapa Gading\"\n",
            ]
            
            # Show current data that can be edited
            editable = [(k, v) for k, v in session.raw_data.items() if not k.startswith("_") and v]
            if editable:
                response_parts.append("\n**Data yang bisa diubah:**\n")
                for field_id, value in editable[:10]:
                    label = field_id
                    for f in all_fields:
                        if f.id == field_id:
                            label = f.label
                            break
                    display_value = str(value)[:50] + "..." if len(str(value)) > 50 else value
                    response_parts.append(f"• {label}: {display_value}\n")
            
            return self._build_result(session, "".join(response_parts))
        
        # Process extracted fields
        updated_fields = []
        errors = []
        
        for field_id, value in extraction_result.items():
            field = self.form_manager.get_field(field_id)
            
            # Try to find via alias if direct lookup fails
            if not field:
                actual_id = FIELD_ALIASES.get(field_id.lower())
                if actual_id:
                    field = self.form_manager.get_field(actual_id)
                    field_id = actual_id
            
            if field:
                is_valid, error_msg, cleaned_value = self.form_manager.validate_field(field_id, value)
                if is_valid:
                    old_value = session.get_field(field_id)
                    session.set_field(field_id, cleaned_value, field.label)
                    updated_fields.append((field.label, old_value, cleaned_value, field_id))
                else:
                    errors.append(f"• {field.label}: {error_msg}")
            else:
                print(f"[EDIT] Field not found: {field_id}")
        
        # Build response
        if updated_fields:
            response_parts = ["✅ **Data berhasil diubah:**\n"]
            for label, old_val, new_val, fid in updated_fields:
                if old_val:
                    response_parts.append(f"• {label}: ~~{old_val}~~ → **{new_val}**\n")
                else:
                    response_parts.append(f"• {label}: **{new_val}** _(baru)_\n")
            
            if errors:
                response_parts.append("\n⚠️ **Tidak valid:**\n")
                for err in errors:
                    response_parts.append(f"{err}\n")
            
            response_parts.append("\nKetik **'summary'** untuk melihat semua data.")
            
            return self._build_result(
                session, 
                "".join(response_parts),
                fields_updated=[fid for _, _, _, fid in updated_fields]
            )
        
        if errors:
            return self._build_result(session, "⚠️ **Validasi gagal:**\n" + "\n".join(errors))
        
        return self._build_result(session, "❌ Tidak ada perubahan yang diterapkan.")
    
    # =========================================================================
    # COMMAND HANDLERS
    # =========================================================================
    
    async def _handle_command(self, session: SessionState, command: str, user_message: str) -> ChatResult:
        """Handle various commands"""
        if command in ["advance", "skip"]:
            return await self._handle_advance(session)
        elif command == "back":
            return await self._handle_back(session)
        elif command == "summary":
            return await self._handle_summary(session)
        elif command == "confirm":
            return await self._handle_confirm_request(session)
        elif command == "reset":
            return await self._handle_reset_request(session)
        elif command == "help":
            return await self._handle_help(session)
        elif command == "check_status":
            reg = self._extract_registration_number(user_message)
            if reg:
                return await self._handle_check_status(session, reg)
            return self._build_result(session, "📋 Masukkan nomor registrasi.\n\nContoh: `AZHAR-2025-TK-ABC12345`")
        return await self._handle_data_input(session, user_message)

    async def _handle_advance(self, session: SessionState) -> ChatResult:
        """Handle advance to next step"""
        current_step = session.current_step
        can_advance = self.form_manager.can_advance_from_step(current_step, session.raw_data)
        
        if not can_advance:
            missing = self.form_manager.get_missing_mandatory_fields(current_step, session.raw_data)
            missing_labels = [f.label for f in missing]
            return self._build_result(session, 
                f"⚠️ Untuk melanjutkan, masih diperlukan:\n• " + "\n• ".join(missing_labels))
        
        next_step = self.form_manager.get_next_step(current_step)
        while next_step and self.form_manager.should_skip_step(next_step.id, session.raw_data):
            next_step = self.form_manager.get_next_step(next_step.id)
        
        if next_step:
            if next_step.id == "documents":
                session.current_step = next_step.id
                session.raw_data["_phase"] = ConversationPhase.UPLOADING_DOCUMENTS.value
                session.raw_data["_current_document_index"] = 0
                transition = self.form_manager.get_step_transition_message(current_step, next_step.id)
                first_doc_prompt = await self._prompt_next_document(session)
                response = transition or "📄 Lanjut ke upload dokumen."
                response += "\n\n" + first_doc_prompt.response
                return self._build_result(session, response)
            
            transition_msg = self.form_manager.get_step_transition_message(current_step, next_step.id)
            session.current_step = next_step.id
            return self._build_result(session, transition_msg or f"✅ Lanjut ke tahap **{next_step.name}**")
        else:
            session.raw_data["_phase"] = ConversationPhase.PRE_CONFIRM.value
            summary = self._format_summary(session)
            return self._build_result(session, f"{summary}\n\n---\n\nKetik **'konfirmasi'** untuk menyelesaikan.")

    async def _handle_back(self, session: SessionState) -> ChatResult:
        """Handle back to previous step"""
        prev_step = self.form_manager.get_previous_step(session.current_step)
        if not prev_step:
            return self._build_result(session, "⚠️ Tidak bisa kembali dari tahap ini.")
        session.current_step = prev_step.id
        session.raw_data["_phase"] = ConversationPhase.COLLECTING.value
        return self._build_result(session, f"⬅️ Kembali ke tahap **{prev_step.name}**")

    async def _handle_summary(self, session: SessionState) -> ChatResult:
        """Handle summary request"""
        return self._build_result(session, self._format_summary(session))

    def _format_summary(self, session: SessionState) -> str:
        """Format registration summary"""
        lines = ["📋 **RINGKASAN DATA PENDAFTARAN**\n"]
        for step in self.form_manager.get_steps():
            if step.id == "review":
                continue
            fields = self.form_manager.get_fields_for_step(step.id)
            step_data = []
            for f in fields:
                value = session.get_field(f.id)
                if value:
                    if f.type == "file":
                        doc_count = session.raw_data.get(f"_doc_count_{f.id}", 1)
                        if doc_count > 1:
                            step_data.append(f"  • {f.label}: ✓ {doc_count} file")
                        else:
                            step_data.append(f"  • {f.label}: ✓ Uploaded")
                    else:
                        step_data.append(f"  • {f.label}: {value}")
            if step_data:
                icon = step.raw_config.get("icon", "📝")
                lines.append(f"{icon} **{step.name}:**")
                lines.extend(step_data)
                lines.append("")
        completion = self.form_manager.calculate_completion(session.raw_data)
        lines.append(f"📊 **Kelengkapan:** {completion:.0f}%")
        return "\n".join(lines)

    async def _handle_help(self, session: SessionState) -> ChatResult:
        """Handle help request"""
        session_context = build_session_context(session, self.form_manager)
        current_step = session_context.get("current_step", {})
        missing_fields = session_context.get("missing_fields", [])
        
        help_text = f"""🆘 **BANTUAN PENDAFTARAN**

📍 **Posisi Anda:** Tahap {current_step.get('name', 'pendaftaran')}

**Perintah yang tersedia:**
• **'lanjut'** - Ke tahap berikutnya
• **'kembali'** - Kembali ke tahap sebelumnya
• **'summary'** - Lihat ringkasan data
• **'konfirmasi'** - Selesaikan pendaftaran
• **'ulang'** - Mulai dari awal
• **'contoh [field]'** - Lihat contoh pengisian

**Cara mengisi data:**
Cukup ketik data langsung, contoh:
• "nama saya Ahmad Fauzi"
• "lahir di Jakarta 15 Mei 2010"
• "alamat Jl. Sudirman No. 10"

**Mengubah data:**
• "ubah nama menjadi Ahmad"
• "ganti alamat ke Jl. Baru"
• "koreksi hp 081234567890"
• "jenjang SD"
"""
        
        if missing_fields:
            help_text += f"\n\n**▶️ Selanjutnya dibutuhkan:** {missing_fields[0].get('label')}"
        
        return self._build_result(session, help_text)
    
    # =========================================================================
    # CONFIRMATION HANDLERS
    # =========================================================================
    
    async def _handle_confirm_request(self, session: SessionState) -> ChatResult:
        """Handle confirmation request"""
        can_confirm, reason = self.form_manager.can_confirm(session.raw_data)
        if not can_confirm:
            return self._build_result(session, f"❌ {reason}\n\nKetik **'summary'** untuk melihat data.")
        summary = self._format_summary(session)
        session.raw_data["_phase"] = ConversationPhase.AWAITING_CONFIRM.value
        return self._build_result(session, f"{summary}\n\n---\n\n⚠️ **KONFIRMASI FINAL**\n\nKetik **'ya saya yakin'** untuk konfirmasi.")

    async def _handle_confirmation_response(self, session: SessionState, user_message: str, user_id: str) -> ChatResult:
        """Handle confirmation response"""
        msg_lower = user_message.lower().strip()
        if any(k in msg_lower for k in ["ya saya yakin", "ya yakin", "yakin", "ya", "iya"]):
            return await self._process_registration(session, user_id)
        else:
            session.raw_data["_phase"] = ConversationPhase.COLLECTING.value
            return self._build_result(session, "Baik, silakan periksa data Anda.\n\nKetik **'summary'** untuk lihat data atau langsung ubah data yang salah.")

    async def _process_registration(self, session: SessionState, user_id: str) -> ChatResult:
        """Process final registration"""
        import uuid
        year = datetime.now().year
        tingkatan = session.get_field("tingkatan") or ""
        code = "TK" if "TK" in tingkatan or "Playgroup" in tingkatan else \
               "SD" if "SD" in tingkatan else \
               "SMP" if "SMP" in tingkatan else \
               "SMA" if "SMA" in tingkatan else "XX"
        unique = str(uuid.uuid4())[:8].upper()
        registration_number = f"AZHAR-{year}-{code}-{unique}"
        
        session.registration_number = registration_number
        session.status = SessionStatus.COMPLETED
        session.raw_data["_phase"] = ConversationPhase.CONFIRMED.value
        session.raw_data["_registration_status"] = "pending_payment"
        
        try:
            from transaksional.app.database import get_db_manager
            db = get_db_manager()
            db.save_registration(session, registration_number, user_id)
        except Exception as e:
            print(f"DB save error: {e}")
        
        response = f"""🎉 **PENDAFTARAN BERHASIL!**

**Nomor Registrasi:** `{registration_number}`

💡 Simpan nomor registrasi untuk cek status.

Ketik **'daftar baru'** untuk pendaftaran lain."""

        session.raw_data["_phase"] = ConversationPhase.ASK_NEW_REGISTRATION.value

        result = self._build_result(session, response)
        result.registration_number = registration_number
        result.registration_status = "pending_payment"
        result.is_complete = True
        return result
    
    # =========================================================================
    # RESET HANDLERS
    # =========================================================================
    
    async def _handle_reset_request(self, session: SessionState) -> ChatResult:
        """Handle reset request"""
        session.raw_data["_phase"] = ConversationPhase.AWAITING_RESET.value
        return self._build_result(session, "⚠️ Anda akan menghapus semua data. Ketik **'ya hapus'** untuk konfirmasi.")

    async def _handle_reset_response(self, session: SessionState, user_message: str) -> ChatResult:
        """Handle reset response"""
        if any(k in user_message.lower() for k in ["ya hapus", "ya reset", "hapus"]):
            first_step = self.form_manager.get_first_step()
            session.current_step = first_step.id if first_step else ""
            session.raw_data = {"_phase": ConversationPhase.COLLECTING.value}
            session.validation_errors = {}
            session.documents_uploaded = {}
            welcome = self.form_manager.get_welcome_message()
            return self._build_result(session, f"🔄 Data berhasil dihapus.\n\n{welcome}")
        session.raw_data["_phase"] = ConversationPhase.COLLECTING.value
        return self._build_result(session, "✅ Baik, data Anda tetap tersimpan.")
    
    # =========================================================================
    # POST-CONFIRMATION HANDLERS
    # =========================================================================
    
    async def _handle_post_confirmation(self, session: SessionState, user_message: str) -> ChatResult:
        """Handle post-confirmation messages"""
        if any(k in user_message.lower() for k in ["daftar baru", "daftar lagi"]):
            first_step = self.form_manager.get_first_step()
            session.current_step = first_step.id if first_step else ""
            session.raw_data = {"_phase": ConversationPhase.COLLECTING.value}
            session.validation_errors = {}
            session.documents_uploaded = {}
            session.registration_number = None
            session.status = SessionStatus.ACTIVE
            welcome = self.form_manager.get_welcome_message()
            return self._build_result(session, f"📝 **PENDAFTARAN BARU**\n\n{welcome}")
        
        reg_number = self._extract_registration_number(user_message)
        if reg_number:
            return await self._handle_check_status(session, reg_number)
        
        return self._build_result(session, f"✅ Nomor registrasi: `{session.registration_number}`\n\nKetik **'daftar baru'** untuk pendaftaran lain.")
    
    # =========================================================================
    # STATUS CHECK HANDLER
    # =========================================================================
    
    async def _handle_check_status(self, session: SessionState, registration_number: str) -> ChatResult:
        """Handle registration status check"""
        try:
            from transaksional.app.database import get_db_manager
            db = get_db_manager()
            reg_data = db.get_registration(registration_number)
        except:
            reg_data = None
        
        if not reg_data:
            return self._build_result(session, f"❌ Nomor `{registration_number}` tidak ditemukan.")
        
        status_labels = {
            "draft": "📝 Draft",
            "pending_payment": "⏳ Menunggu Pembayaran",
            "payment_uploaded": "📤 Bukti Pembayaran Diterima",
            "payment_verified": "✅ Pembayaran Terverifikasi",
            "documents_review": "📋 Dokumen Direview",
            "approved": "🎉 Disetujui",
            "rejected": "❌ Ditolak"
        }
        
        status = reg_data.get("status", "pending_payment")
        student_data = reg_data.get("student_data", {})
        
        result = self._build_result(session, f"""📋 **STATUS PENDAFTARAN**

**Nomor:** `{registration_number}`
**Nama:** {student_data.get("nama_lengkap", "-")}
**Status:** {status_labels.get(status, status)}""")
        
        result.registration_number = registration_number
        result.registration_status = status
        return result
    
    # =========================================================================
    # DOCUMENT UPLOAD HANDLERS
    # =========================================================================
    
    def _get_document_fields_ordered(self) -> List[FieldConfig]:
        """Get document fields ordered"""
        doc_fields = self.form_manager.get_fields_for_step("documents")
        return sorted(doc_fields, key=lambda f: f.raw_config.get("order", 999))

    async def _handle_document_phase(self, session: SessionState, user_message: str, 
                                     file_path: str = None, file_info: Dict = None) -> ChatResult:
        """Handle document upload phase"""
        msg_lower = user_message.lower().strip()
        
        if msg_lower in ["skip", "lewati", "tidak ada", "kosong"]:
            return await self._handle_skip_document(session)
        
        command = self.form_manager.detect_command(user_message)
        if command == "back":
            session.raw_data["_phase"] = ConversationPhase.COLLECTING.value
            return await self._handle_back(session)
        elif command == "summary":
            return await self._handle_summary(session)
        
        if file_path and file_info:
            return await self._handle_smart_document_upload(session, file_path, file_info)
        
        return await self._prompt_next_document(session)

    async def _prompt_next_document(self, session: SessionState) -> ChatResult:
        """Prompt user to upload documents"""
        doc_fields = self._get_document_fields_ordered()
        
        uploaded_fields = [f for f in doc_fields if session.get_field(f.id)]
        missing_mandatory = [f for f in doc_fields if f.is_mandatory and not session.get_field(f.id)]
        missing_optional = [f for f in doc_fields if not f.is_mandatory and not session.get_field(f.id)]
        
        if not missing_mandatory:
            return await self._finish_document_upload(session)
        
        prompt_parts = ["📄 **UPLOAD DOKUMEN**\n"]
        prompt_parts.append("💡 **Tips:** Upload semua dokumen sekaligus! Sistem akan otomatis mengenali jenisnya.\n")
        
        prompt_parts.append("**Dokumen yang masih diperlukan:**")
        for f in missing_mandatory:
            prompt_parts.append(f"  ❗ {f.label} *(wajib)*")
        
        if missing_optional:
            prompt_parts.append("\n**Opsional:**")
            for f in missing_optional[:3]:
                prompt_parts.append(f"  ○ {f.label}")
        
        uploaded_count = len(uploaded_fields)
        total_mandatory = sum(1 for f in doc_fields if f.is_mandatory)
        uploaded_mandatory = sum(1 for f in uploaded_fields if f.is_mandatory)
        
        prompt_parts.append(f"\n📊 Progress: {uploaded_mandatory}/{total_mandatory} dokumen wajib")
        
        if uploaded_fields:
            prompt_parts.append("\n**Sudah diupload:**")
            for f in uploaded_fields[:5]:
                count = session.raw_data.get(f"_doc_count_{f.id}", 1)
                prompt_parts.append(f"  ✅ {f.label}" + (f" ({count} file)" if count > 1 else ""))
        
        return self._build_result(session, "\n".join(prompt_parts))

    async def _handle_smart_document_upload(self, session: SessionState, file_path: str, 
                                            file_info: Dict = None) -> ChatResult:
        """Handle document upload with smart classification"""
        from transaksional.app.document_classifier import get_document_classifier, DocumentType
        
        classifier = get_document_classifier()
        doc_fields = self._get_document_fields_ordered()
        
        is_batch = file_info and file_info.get("batch_id") and file_info.get("all_files")
        
        if is_batch:
            all_files = file_info.get("all_files", [])
            classifications = await classifier.classify_batch(all_files, use_vision=True)
            
            grouped = {}
            unclassified = []
            
            for cls_result in classifications:
                if cls_result.detected_type == DocumentType.UNKNOWN:
                    unclassified.append(cls_result)
                else:
                    field_id = classifier.get_field_id_for_type(cls_result.detected_type)
                    if field_id not in grouped:
                        grouped[field_id] = []
                    grouped[field_id].append(cls_result)
            
            response_parts = ["📎 **Dokumen berhasil diupload & dikenali:**\n"]
            
            for field_id, files in grouped.items():
                field = next((f for f in doc_fields if f.id == field_id), None)
                if not field:
                    continue
                
                session.set_field(field_id, files[0].file_path, field.label)
                session.raw_data[f"_doc_count_{field_id}"] = len(files)
                
                if len(files) > 1:
                    response_parts.append(f"✅ **{field.label}:** {len(files)} file")
                else:
                    response_parts.append(f"✅ **{field.label}:** {files[0].original_name}")
            
            if unclassified:
                response_parts.append(f"\n⚠️ **{len(unclassified)} file tidak dikenali:**")
                for f in unclassified[:3]:
                    response_parts.append(f"  • {f.original_name}")
                if len(unclassified) > 3:
                    response_parts.append(f"  ... dan {len(unclassified) - 3} lainnya")
                response_parts.append("\n💡 Coba rename file dengan nama yang lebih jelas")
            
            next_result = await self._prompt_next_document(session)
            response_parts.append("\n---\n")
            response_parts.append(next_result.response)
            
            return self._build_result(session, "\n".join(response_parts))
        
        else:
            original_name = file_info.get("original_name", "") if file_info else ""
            cls_result = await classifier.classify_single(file_path, original_name, use_vision=True)
            
            if cls_result.detected_type == DocumentType.UNKNOWN:
                current_index = session.raw_data.get("_current_document_index", 0)
                if current_index < len(doc_fields):
                    field = doc_fields[current_index]
                    field_id = field.id
                else:
                    return self._build_result(session, 
                        f"❓ Tidak dapat mengenali jenis dokumen **{original_name}**.\n\n"
                        "Mohon rename file dengan nama yang lebih jelas, contoh:\n"
                        "• akta_kelahiran.pdf\n"
                        "• kartu_keluarga.jpg")
            else:
                field_id = classifier.get_field_id_for_type(cls_result.detected_type)
            
            field = next((f for f in doc_fields if f.id == field_id), None)
            if not field:
                return self._build_result(session, f"❌ Jenis dokumen tidak valid: {field_id}")
            
            allowed_ext = field.raw_config.get("allowed_extensions", [".pdf", ".jpg", ".jpeg", ".png"])
            file_ext = "." + file_path.split(".")[-1].lower() if "." in file_path else ""
            
            if file_ext not in allowed_ext:
                return self._build_result(session, 
                    f"❌ Format tidak didukung untuk {field.label}. Gunakan: {', '.join(allowed_ext)}")
            
            session.set_field(field_id, file_path, field.label)
            session.raw_data[f"_doc_count_{field_id}"] = 1
            
            confidence_text = ""
            if cls_result.confidence < 0.7:
                confidence_text = f" *(confidence: {cls_result.confidence:.0%})*"
            
            success_msg = f"✅ **{field.label}** berhasil diupload!{confidence_text}"
            
            next_result = await self._prompt_next_document(session)
            
            return self._build_result(session, f"{success_msg}\n\n{next_result.response}")

    async def _handle_skip_document(self, session: SessionState) -> ChatResult:
        """Handle skip document"""
        doc_fields = self._get_document_fields_ordered()
        missing_mandatory = [f for f in doc_fields if f.is_mandatory and not session.get_field(f.id)]
        
        if missing_mandatory:
            return self._build_result(session, 
                f"❌ Masih ada dokumen wajib yang belum diupload:\n• " + 
                "\n• ".join([f.label for f in missing_mandatory]))
        
        return await self._finish_document_upload(session)

    async def _finish_document_upload(self, session: SessionState) -> ChatResult:
        """Finish document upload phase"""
        doc_fields = self._get_document_fields_ordered()
        
        missing_mandatory = [f for f in doc_fields if f.is_mandatory and not session.get_field(f.id)]
        if missing_mandatory:
            return self._build_result(session, 
                f"⚠️ Dokumen wajib belum lengkap:\n• " + "\n• ".join([f.label for f in missing_mandatory]))
        
        uploaded_items = []
        skipped_items = []
        
        for f in doc_fields:
            if session.get_field(f.id):
                doc_count = session.raw_data.get(f"_doc_count_{f.id}", 1)
                if doc_count > 1:
                    uploaded_items.append(f"✅ {f.label} ({doc_count} file)")
                else:
                    uploaded_items.append(f"✅ {f.label}")
            else:
                skipped_items.append(f"⏭️ {f.label}")
        
        summary = "📋 **Dokumen:**\n" + "\n".join(uploaded_items)
        if skipped_items:
            summary += "\n\n**Dilewati:**\n" + "\n".join(skipped_items)
        
        session.raw_data["_phase"] = ConversationPhase.PRE_CONFIRM.value
        session.current_step = "review"
        
        return self._build_result(session, 
            f"{summary}\n\n---\n\n✅ Upload selesai!\n\nKetik **'konfirmasi'** untuk menyelesaikan.")
    
    # =========================================================================
    # LLM EXTRACTION HELPER
    # =========================================================================
    
    async def _extract_fields_with_llm(self, message: str, fields: List[FieldConfig], 
                                       session: SessionState) -> Dict:
        """Extract fields using LLM"""
        try:
            fields_dict = [
                {
                    "id": f.id,
                    "label": f.label,
                    "type": f.type,
                    "examples": f.examples,
                    "options": f.options,
                    "extract_keywords": f.extract_keywords
                }
                for f in fields
            ]
            
            recent = session.get_recent_messages(5)
            context = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
            
            result = await self.llm.extract_fields(message, context, fields_dict)
            return result if result else {}
        except Exception as e:
            print(f"LLM extraction error: {e}")
            return {}
    
    # =========================================================================
    # RESPONSE BUILDERS
    # =========================================================================
    
    def _build_input_response(self, session: SessionState, confirmed_values: List, 
                             validation_errors: Dict, current_step: str) -> str:
        """Build response for data input"""
        parts = []
        
        if confirmed_values:
            for field, value, action in confirmed_values:
                parts.append(f"✓ {field.label}: **{value}**")
        
        if validation_errors:
            for field_id, error in validation_errors.items():
                field = self.form_manager.get_field(field_id)
                parts.append(f"❌ {field.label if field else field_id}: {error}")
        
        can_advance = self.form_manager.can_advance_from_step(current_step, session.raw_data)
        
        if can_advance:
            parts.append("\n✅ Data tahap ini sudah cukup! Ketik **'lanjut'** untuk melanjutkan.")
        else:
            missing = self.form_manager.get_missing_mandatory_fields(current_step, session.raw_data)
            if missing:
                nf = missing[0]
                example = f" _(Contoh: {nf.examples[0]})_" if nf.examples else ""
                parts.append(f"\n▶️ Selanjutnya, **{nf.label}**?{example}")
        
        return "\n".join(parts)

    def _build_result(self, session: SessionState, response: str, 
                     fields_updated: List[str] = None, fields_created: List[str] = None,
                     validation_errors: Dict[str, str] = None) -> ChatResult:
        """Build ChatResult"""
        completion = self.form_manager.calculate_completion(session.raw_data)
        can_advance = self.form_manager.can_advance_from_step(session.current_step, session.raw_data)
        can_confirm, _ = self.form_manager.can_confirm(session.raw_data)
        
        prev_step = self.form_manager.get_previous_step(session.current_step)
        can_go_back = prev_step is not None
        
        steps = self.form_manager.get_steps()
        current_step_obj = self.form_manager.get_step(session.current_step)
        step_info = {
            "current": session.current_step,
            "current_name": current_step_obj.name if current_step_obj else "",
            "current_index": next((i for i, s in enumerate(steps) if s.id == session.current_step), 0),
            "total_steps": len(steps),
            "steps": [{"id": s.id, "name": s.name, "icon": s.raw_config.get("icon", "")} for s in steps]
        }
        
        doc_fields = self._get_document_fields_ordered()
        documents_status = {
            "total": len(doc_fields),
            "mandatory": sum(1 for f in doc_fields if f.is_mandatory),
            "uploaded": sum(1 for f in doc_fields if session.get_field(f.id)),
            "mandatory_uploaded": sum(1 for f in doc_fields if f.is_mandatory and session.get_field(f.id)),
            "documents": [
                {
                    "field_id": f.id, 
                    "label": f.label, 
                    "is_mandatory": f.is_mandatory,
                    "is_uploaded": session.get_field(f.id) is not None,
                    "file_count": session.raw_data.get(f"_doc_count_{f.id}", 1 if session.get_field(f.id) else 0)
                }
                for f in doc_fields
            ]
        }
        
        return ChatResult(
            response=response,
            session_id=session.session_id,
            current_step=session.current_step,
            phase=session.raw_data.get("_phase", ConversationPhase.COLLECTING.value),
            completion_percentage=completion,
            fields_updated=fields_updated or [],
            fields_created=fields_created or [],
            validation_errors=validation_errors or session.validation_errors,
            can_advance=can_advance,
            can_confirm=can_confirm,
            can_go_back=can_go_back,
            is_complete=session.status == SessionStatus.COMPLETED,
            registration_number=session.registration_number,
            registration_status=session.raw_data.get("_registration_status"),
            step_info=step_info,
            documents_status=documents_status,
            metadata={
                "message_count": len(session.conversation_history), 
                "edit_count": len(session.edit_history)
            }
        )


# =============================================================================
# SINGLETON
# =============================================================================

_chat_handler: Optional[ChatHandler] = None

def get_chat_handler() -> ChatHandler:
    """Get singleton chat handler"""
    global _chat_handler
    if _chat_handler is None:
        _chat_handler = ChatHandler()
    return _chat_handler