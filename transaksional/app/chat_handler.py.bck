from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import re

from transaksional.app.form_manager import get_form_manager, DynamicFormManager, FieldConfig
from transaksional.app.session_state import SessionState, SessionManager, get_session_manager, SessionStatus
from transaksional.app.llm_client import get_llm, BaseLLMClient


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


class ChatHandler:
    def __init__(self):
        self.form_manager: DynamicFormManager = get_form_manager()
        self.session_manager: SessionManager = get_session_manager()
        self.llm: BaseLLMClient = get_llm()
    
    async def process_message(self, session_id: str, user_message: str, 
                              file_path: str = None, file_info: Dict = None,user_id: str= None ) -> ChatResult:
        session = self._get_or_create_session(session_id)
        session.add_message("user", user_message)
        
        current_phase = session.raw_data.get("_phase", ConversationPhase.COLLECTING.value)
        print(f"Processing message in phase: {current_phase}")
        
        # Check for registration number (status check)
       
        reg_number = self._extract_registration_number(user_message)
        print(reg_number)
        if reg_number:
            result = await self._handle_check_status(session, reg_number)
        elif current_phase == ConversationPhase.UPLOADING_DOCUMENTS.value:
            result = await self._handle_document_phase(session, user_message, file_path, file_info)
        elif current_phase == ConversationPhase.AWAITING_CONFIRM.value:
            result = await self._handle_confirmation_response(session, user_message,user_id)
        elif current_phase == ConversationPhase.AWAITING_RESET.value:
            result = await self._handle_reset_response(session, user_message)
        elif current_phase == ConversationPhase.ASK_NEW_REGISTRATION.value:
            result = await self._handle_post_confirmation(session, user_message)
        elif current_phase == ConversationPhase.CONFIRMED.value:
            result = await self._handle_post_confirmation(session, user_message)
        else:
            # Check for edit request first - LLM will understand context
            if await self._is_edit_request(user_message, session):
                result = await self._handle_edit_request(session, user_message)
            else:
                command = self.form_manager.detect_command(user_message)
                print(f"Detected command: {command}")
                if command:
                    result = await self._handle_command(session, command, user_message)
                else:
                    print("No command detected, handling as data input.")
                    result = await self._handle_data_input(session, user_message)
        
        self.session_manager.save_session(session)
        print(f"Chat response: {result.response}")
        session.add_message("assistant", result.response)
        return result
    
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
        """Check if user wants to edit data using LLM understanding"""
        edit_keywords = ["ubah", "ganti", "koreksi", "perbaiki", "salah", "edit", "update", 
                        "ralat", "bukan", "harusnya", "seharusnya", "yang benar"]
        message_lower = message.lower()
        return any(kw in message_lower for kw in edit_keywords)

    async def _handle_edit_request(self, session: SessionState, user_message: str) -> ChatResult:
        """Handle edit request - LLM understands what to change"""
        # Get ALL fields from all steps for editing
        all_fields = self.form_manager.get_all_fields()
        
        # Use LLM to understand what user wants to change
        extraction_result = await self._extract_fields_with_llm(user_message, all_fields, session)
        
        if not extraction_result:
            return self._build_result(session, 
                "Maaf, saya tidak mengerti data mana yang ingin diubah.\n\n"
                "Contoh cara mengubah:\n"
                "• \"ubah nama menjadi Ahmad Fauzi\"\n"
                "• \"ganti alamat ke Jl. Sudirman No. 10\"\n"
                "• \"koreksi tanggal lahir 15/05/2000\"\n"
                "• \"nama ayah budi, ibu siti\" (ubah sekaligus)")
        
        # Apply changes
        updated_fields = []
        for field_id, value in extraction_result.items():
            field = self.form_manager.get_field(field_id)
            if field:
                is_valid, error_msg, cleaned_value = self.form_manager.validate_field(field_id, value)
                if is_valid:
                    old_value = session.get_field(field_id)
                    session.set_field(field_id, cleaned_value, field.label)
                    updated_fields.append((field.label, old_value, cleaned_value))
        
        if updated_fields:
            response_parts = ["✅ **Data berhasil diubah:**\n"]
            for label, old_val, new_val in updated_fields:
                if old_val:
                    response_parts.append(f"• {label}: ~~{old_val}~~ → **{new_val}**")
                else:
                    response_parts.append(f"• {label}: **{new_val}**")
            
            response_parts.append("\nKetik **'summary'** untuk melihat semua data.")
            return self._build_result(session, "\n".join(response_parts))
        
        return self._build_result(session, "Tidak ada perubahan yang diterapkan.")

    async def _handle_command(self, session: SessionState, command: str, user_message: str) -> ChatResult:
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
            return self._build_result(session, "Masukkan nomor registrasi.\nContoh: `AZHAR-2025-TK-ABC12345`")
        return await self._handle_data_input(session, user_message)

    async def _handle_advance(self, session: SessionState) -> ChatResult:
        current_step = session.current_step
        can_advance = self.form_manager.can_advance_from_step(current_step, session.raw_data)
        
        if not can_advance:
            missing = self.form_manager.get_missing_mandatory_fields(current_step, session.raw_data)
            missing_labels = [f.label for f in missing]
            return self._build_result(session, f"⚠️ Untuk melanjutkan, masih diperlukan:\n• " + "\n• ".join(missing_labels))
        
        next_step = self.form_manager.get_next_step(current_step)
        while next_step and self.form_manager.should_skip_step(next_step.id, session.raw_data):
            next_step = self.form_manager.get_next_step(next_step.id)
        
        if next_step:
            if next_step.id == "documents":
                session.current_step = next_step.id
                session.raw_data["_phase"] = ConversationPhase.UPLOADING_DOCUMENTS.value
                session.raw_data["_current_document_index"] = 0
                transition = self.form_manager.get_step_transition_message(current_step, next_step.id)
                return self._build_result(session, transition or "Lanjut ke upload dokumen.")
            
            transition_msg = self.form_manager.get_step_transition_message(current_step, next_step.id)
            session.current_step = next_step.id
            return self._build_result(session, transition_msg or f"Lanjut ke tahap **{next_step.name}**")
        else:
            session.raw_data["_phase"] = ConversationPhase.PRE_CONFIRM.value
            summary = self._format_summary(session)
            return self._build_result(session, f"{summary}\n\n---\n\nKetik **'konfirmasi'** untuk menyelesaikan.")

    async def _handle_back(self, session: SessionState) -> ChatResult:
        prev_step = self.form_manager.get_previous_step(session.current_step)
        if not prev_step:
            return self._build_result(session, "Tidak bisa kembali dari tahap ini.")
        session.current_step = prev_step.id
        session.raw_data["_phase"] = ConversationPhase.COLLECTING.value
        return self._build_result(session, f"⬅️ Kembali ke tahap **{prev_step.name}**")

    async def _handle_summary(self, session: SessionState) -> ChatResult:
        return self._build_result(session, self._format_summary(session))

    def _format_summary(self, session: SessionState) -> str:
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
        return self._build_result(session, """🆘 **BANTUAN**

**Perintah:**
• **'lanjut'** - Ke tahap berikutnya
• **'back'** - Kembali ke tahap sebelumnya
• **'summary'** - Lihat ringkasan data
• **'konfirmasi'** - Selesaikan pendaftaran
• **'ulang'** - Mulai dari awal
• **'help'** - Tampilkan bantuan

**Mengubah Data:**
• \"ubah nama menjadi Ahmad\"
• \"ganti alamat ke Jl. Baru\"
• \"koreksi tanggal lahir 15/05/2000\"""")

    async def _handle_confirm_request(self, session: SessionState) -> ChatResult:
        can_confirm, reason = self.form_manager.can_confirm(session.raw_data)
        if not can_confirm:
            return self._build_result(session, f"❌ {reason}\n\nKetik **'summary'** untuk melihat data.")
        summary = self._format_summary(session)
        session.raw_data["_phase"] = ConversationPhase.AWAITING_CONFIRM.value
        return self._build_result(session, f"{summary}\n\n---\n\n⚠️ **KONFIRMASI FINAL**\n\nKetik **'ya saya yakin'** untuk konfirmasi.")

    async def _handle_confirmation_response(self, session: SessionState, user_message: str, user_id: str) -> ChatResult:
        msg_lower = user_message.lower().strip()
        if any(k in msg_lower for k in ["ya saya yakin", "ya yakin", "yakin", "ya", "iya"]):
            return await self._process_registration(session, user_id)
        else:
            session.raw_data["_phase"] = ConversationPhase.COLLECTING.value
            return self._build_result(session, "Baik, silakan periksa data Anda.\n\nKetik **'summary'** untuk lihat data atau langsung ubah data yang salah.")

    async def _process_registration(self, session: SessionState, user_id: str) -> ChatResult:
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
            from  transaksional.app.database import get_db_manager
            db = get_db_manager()
            db.save_registration(session, registration_number,user_id)
        except Exception as e:
            print(f"DB save error: {e}")
        
        payment_info = self._build_payment_info(registration_number, tingkatan)
        
        response = f"""🎉 **PENDAFTARAN BERHASIL!**

**Nomor Registrasi:** `{registration_number}`

{payment_info}

💡 Simpan nomor registrasi untuk cek status.

Ketik **'daftar baru'** untuk pendaftaran lain."""
        
        session.raw_data["_phase"] = ConversationPhase.ASK_NEW_REGISTRATION.value
        
        result = self._build_result(session, response)
        result.registration_number = registration_number
        result.registration_status = "pending_payment"
        result.is_complete = True
        return result

    def _build_payment_info(self, registration_number: str, tingkatan: str) -> str:
        payment_config = self.form_manager.config.get("payment_info", {})
        biaya_config = payment_config.get("biaya_pendaftaran", {})
        bank_config = payment_config.get("payment_method", {}).get("bank_transfer", {})
        
        code = "TK" if "TK" in tingkatan or "Playgroup" in tingkatan else \
               "SD" if "SD" in tingkatan else \
               "SMP" if "SMP" in tingkatan else \
               "SMA" if "SMA" in tingkatan else "default"
        
        biaya = biaya_config.get(code, biaya_config.get("default", 500000))
        biaya_formatted = f"Rp {biaya:,.0f}".replace(",", ".")
        
        deadline_days = payment_config.get("payment_deadline_days", 3)
        deadline = (datetime.now() + timedelta(days=deadline_days)).strftime("%d %B %Y")
        
        return f"""💳 **INFORMASI PEMBAYARAN**

**Biaya:** {biaya_formatted}
**Batas Waktu:** {deadline}

**Transfer ke:**
🏦 {bank_config.get("bank_name", "Bank Mandiri")}
📝 No. Rek: {bank_config.get("account_number", "123-456-789")}
👤 A.N: {bank_config.get("account_name", "YPI Al-Azhar")}

⚠️ Cantumkan `{registration_number}` pada berita transfer"""

    async def _handle_reset_request(self, session: SessionState) -> ChatResult:
        session.raw_data["_phase"] = ConversationPhase.AWAITING_RESET.value
        return self._build_result(session, "⚠️ Anda akan menghapus semua data. Ketik **'ya hapus'** untuk konfirmasi.")

    async def _handle_reset_response(self, session: SessionState, user_message: str) -> ChatResult:
        if any(k in user_message.lower() for k in ["ya hapus", "ya reset", "hapus"]):
            first_step = self.form_manager.get_first_step()
            session.current_step = first_step.id if first_step else ""
            session.raw_data = {"_phase": ConversationPhase.COLLECTING.value}
            session.validation_errors = {}
            session.documents_uploaded = {}
            welcome = self.form_manager.get_welcome_message()
            return self._build_result(session, f"🔄 Data berhasil dihapus.\n\n{welcome}")
        session.raw_data["_phase"] = ConversationPhase.COLLECTING.value
        return self._build_result(session, "Baik, data Anda tetap tersimpan.")

    async def _handle_post_confirmation(self, session: SessionState, user_message: str) -> ChatResult:
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
        
        return self._build_result(session, f"Nomor registrasi: `{session.registration_number}`\n\nKetik **'daftar baru'** untuk pendaftaran lain.")

    async def _handle_check_status(self, session: SessionState, registration_number: str) -> ChatResult:
        try:
            from app.database import get_db_manager
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

    # DOCUMENT UPLOAD HANDLERS
    def _get_document_fields_ordered(self) -> List[FieldConfig]:
        doc_fields = self.form_manager.get_fields_for_step("documents")
        return sorted(doc_fields, key=lambda f: f.raw_config.get("order", 999))

    async def _handle_document_phase(self, session: SessionState, user_message: str, 
                                     file_path: str = None, file_info: Dict = None) -> ChatResult:
        msg_lower = user_message.lower().strip()
        
        if msg_lower in ["skip", "lewati", "tidak ada", "kosong"]:
            return await self._handle_skip_document(session)
        
        command = self.form_manager.detect_command(user_message)
        if command == "back":
            session.raw_data["_phase"] = ConversationPhase.COLLECTING.value
            return await self._handle_back(session)
        elif command == "summary":
            return await self._handle_summary(session)
        
        if file_path:
            return await self._handle_document_upload(session, file_path, file_info)
        
        return await self._prompt_next_document(session)

    async def _prompt_next_document(self, session: SessionState) -> ChatResult:
        doc_fields = self._get_document_fields_ordered()
        current_index = session.raw_data.get("_current_document_index", 0)
        
        while current_index < len(doc_fields):
            field = doc_fields[current_index]
            if not session.get_field(field.id):
                break
            current_index += 1
        
        session.raw_data["_current_document_index"] = current_index
        
        if current_index >= len(doc_fields):
            return await self._finish_document_upload(session)
        
        field = doc_fields[current_index]
        prompt = field.raw_config.get("prompt_message", f"📄 Upload **{field.label}**")
        
        if not field.is_mandatory:
            prompt += "\n\n💡 Ketik **'skip'** untuk melewati."
        
        uploaded = sum(1 for f in doc_fields if session.get_field(f.id))
        total = len(doc_fields)
        progress = f"\n\n📊 Progress: {uploaded}/{total} dokumen"
        
        return self._build_result(session, prompt + progress)

    async def _handle_document_upload(self, session: SessionState, file_path: str, file_info: Dict = None) -> ChatResult:
        doc_fields = self._get_document_fields_ordered()
        current_index = session.raw_data.get("_current_document_index", 0)
        
        if current_index >= len(doc_fields):
            return await self._finish_document_upload(session)
        
        field = doc_fields[current_index]
        
        allowed_ext = field.raw_config.get("allowed_extensions", [".pdf", ".jpg", ".jpeg", ".png"])
        file_ext = "." + file_path.split(".")[-1].lower() if "." in file_path else ""
        
        if file_ext not in allowed_ext:
            return self._build_result(session, f"❌ Format tidak didukung. Gunakan: {', '.join(allowed_ext)}")
        
        session.set_field(field.id, file_path, field.label)
        if file_info:
            session.set_document(field.id, file_info)
        
        try:
            from  transaksional.app.database import get_db_manager
            db = get_db_manager()
            db.save_document(
                session_id=session.session_id,
                field_name=field.id,
                file_name=file_info.get("file_name", "") if file_info else "",
                file_path=file_path,
                file_size=file_info.get("file_size", 0) if file_info else 0,
                file_type=file_info.get("content_type", "") if file_info else ""
            )
        except Exception as e:
            print(f"DB save doc error: {e}")
        
        success_msg = field.raw_config.get("success_message", f"✅ {field.label} berhasil!")
        session.raw_data["_current_document_index"] = current_index + 1
        
        next_result = await self._prompt_next_document(session)
        return self._build_result(session, f"{success_msg}\n\n{next_result.response}")

    async def _handle_skip_document(self, session: SessionState) -> ChatResult:
        doc_fields = self._get_document_fields_ordered()
        current_index = session.raw_data.get("_current_document_index", 0)
        
        if current_index >= len(doc_fields):
            return await self._finish_document_upload(session)
        
        field = doc_fields[current_index]
        
        if field.is_mandatory:
            return self._build_result(session, f"❌ **{field.label}** wajib diupload.")
        
        session.raw_data["_current_document_index"] = current_index + 1
        next_result = await self._prompt_next_document(session)
        return self._build_result(session, f"⏭️ {field.label} dilewati.\n\n{next_result.response}")

    async def _finish_document_upload(self, session: SessionState) -> ChatResult:
        doc_fields = self._get_document_fields_ordered()
        
        missing_mandatory = [f for f in doc_fields if f.is_mandatory and not session.get_field(f.id)]
        if missing_mandatory:
            for i, f in enumerate(doc_fields):
                if f in missing_mandatory:
                    session.raw_data["_current_document_index"] = i
                    break
            return self._build_result(session, f"⚠️ Dokumen wajib belum lengkap:\n• " + "\n• ".join([f.label for f in missing_mandatory]))
        
        uploaded = [f"✅ {f.label}" for f in doc_fields if session.get_field(f.id)]
        skipped = [f"⏭️ {f.label}" for f in doc_fields if not session.get_field(f.id)]
        
        summary = "📋 **Dokumen:**\n" + "\n".join(uploaded)
        if skipped:
            summary += "\n\n**Dilewati:**\n" + "\n".join(skipped)
        
        session.raw_data["_phase"] = ConversationPhase.PRE_CONFIRM.value
        session.current_step = "review"
        
        return self._build_result(session, f"{summary}\n\n---\n\n✅ Upload selesai!\n\nKetik **'konfirmasi'** untuk menyelesaikan.")

    # DATA INPUT HANDLERS
    async def _handle_data_input(self, session: SessionState, user_message: str) -> ChatResult:
        current_step = session.current_step
        fields = self.form_manager.get_fields_for_step(current_step)
        
        # Always try LLM first
        extraction_result = await self._extract_fields_with_llm(user_message, fields, session)
        
        # Fallback to simple extraction only if LLM returns nothing
        if not extraction_result:
            print("LLM extraction returned nothing, using simple extraction.")
            extraction_result = self.form_manager.extract_fields_simple(user_message, fields)
        
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
        
        response = self._build_input_response(session, confirmed_values, validation_errors, current_step)
        
        return self._build_result(session, response,
                                 fields_updated=[f.id for f, _, a in confirmed_values if a == "update"],
                                 fields_created=[f.id for f, _, a in confirmed_values if a == "create"],
                                 validation_errors=validation_errors)

    async def _extract_fields_with_llm(self, message: str, fields: List[FieldConfig], session: SessionState) -> Dict:
        """Extract fields using LLM with proper parameters"""
        try:
            # Convert FieldConfig objects to dict for LLM
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
            
            # Build context from recent messages
            recent = session.get_recent_messages(5)
            context = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
            
            result = await self.llm.extract_fields(message, context, fields_dict)
            return result if result else {}
        except Exception as e:
            print(f"LLM extraction error: {e}")
            return {}

    def _build_input_response(self, session: SessionState, confirmed_values: List, 
                             validation_errors: Dict, current_step: str) -> str:
        parts = []
        
        if confirmed_values:
            for field, value, action in confirmed_values:
                parts.append(f"✓ {field.label}: {value}")
        
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
                example = f" (Contoh: {nf.examples[0]})" if nf.examples else ""
                parts.append(f"\nSelanjutnya, {nf.label}?{example}")
        
        if not confirmed_values and not validation_errors:
            parts.append("Maaf, saya tidak menangkap informasi.")
            missing = self.form_manager.get_missing_mandatory_fields(current_step, session.raw_data)
            if missing:
                nf = missing[0]
                parts.append(f"Mohon berikan {nf.label}.")
        
        return "\n".join(parts)

    def _build_result(self, session: SessionState, response: str, 
                     fields_updated: List[str] = None, fields_created: List[str] = None,
                     validation_errors: Dict[str, str] = None) -> ChatResult:
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
                {"field_id": f.id, "label": f.label, "is_mandatory": f.is_mandatory,
                 "is_uploaded": session.get_field(f.id) is not None}
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
            metadata={"message_count": len(session.conversation_history), "edit_count": len(session.edit_history)}
        )


_chat_handler: Optional[ChatHandler] = None

def get_chat_handler() -> ChatHandler:
    global _chat_handler
    if _chat_handler is None:
        _chat_handler = ChatHandler()
    return _chat_handler