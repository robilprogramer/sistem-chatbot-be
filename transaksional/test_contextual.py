"""
Test Script untuk Contextual Understanding
==========================================
Jalankan dengan: python test_contextual.py

Pastikan sudah set environment variables:
- OPENAI_API_KEY atau ANTHROPIC_API_KEY
- DATABASE_URL (optional)
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()


# =============================================================================
# MOCK OBJECTS untuk testing tanpa full system
# =============================================================================

class MockFieldConfig:
    def __init__(self, id, label, type="text", examples=None, tips="", is_mandatory=True):
        self.id = id
        self.label = label
        self.type = type
        self.examples = examples or []
        self.tips = tips
        self.is_mandatory = is_mandatory
        self.options = []
        self.extract_keywords = []
        self.raw_config = {}


class MockSession:
    def __init__(self):
        self.session_id = "test-session-001"
        self.current_step = "data_siswa"
        self.raw_data = {
            "_phase": "collecting",
            # Data yang sudah diisi (contoh)
            "nama_lengkap": "Ahmad Fauzi",
        }
        self.validation_errors = {}
        self.conversation_history = []
        self.registration_number = None
    
    def get_field(self, field_id, default=None):
        return self.raw_data.get(field_id, default)
    
    def get_recent_messages(self, count=5):
        return self.conversation_history[-count:]


class MockFormManager:
    def __init__(self):
        self.fields = {
            "nama_lengkap": MockFieldConfig("nama_lengkap", "Nama Lengkap Siswa", 
                                           examples=["Ahmad Fauzi", "Siti Nurhaliza"]),
            "tempat_lahir": MockFieldConfig("tempat_lahir", "Tempat Lahir",
                                           examples=["Jakarta", "Bandung", "Surabaya"]),
            "tanggal_lahir": MockFieldConfig("tanggal_lahir", "Tanggal Lahir", type="date",
                                            examples=["15/05/2010", "20/03/2012"],
                                            tips="Format: DD/MM/YYYY"),
            "jenis_kelamin": MockFieldConfig("jenis_kelamin", "Jenis Kelamin", type="select",
                                            examples=["Laki-laki", "Perempuan"]),
            "alamat": MockFieldConfig("alamat", "Alamat Lengkap",
                                     examples=["Jl. Sudirman No. 10, Jakarta Selatan"]),
        }
        
        self.steps = [
            {"id": "data_siswa", "name": "Data Siswa", "description": "Informasi dasar siswa", "order": 1},
            {"id": "data_ortu", "name": "Data Orang Tua", "description": "Informasi orang tua/wali", "order": 2},
            {"id": "documents", "name": "Upload Dokumen", "description": "Upload dokumen pendukung", "order": 3},
        ]
    
    def get_step(self, step_id):
        for s in self.steps:
            if s["id"] == step_id:
                return type('Step', (), {
                    'id': s["id"],
                    'name': s["name"],
                    'description': s["description"],
                    'raw_config': {"icon": "📝"}
                })()
        return None
    
    def get_steps(self):
        return [self.get_step(s["id"]) for s in self.steps]
    
    def get_step_index(self, step_id):
        for i, s in enumerate(self.steps):
            if s["id"] == step_id:
                return i
        return 0
    
    def get_fields_for_step(self, step_id):
        if step_id == "data_siswa":
            return list(self.fields.values())
        return []
    
    def get_missing_mandatory_fields(self, step_id, raw_data):
        fields = self.get_fields_for_step(step_id)
        return [f for f in fields if f.is_mandatory and not raw_data.get(f.id)]
    
    def calculate_completion(self, raw_data):
        total = len(self.fields)
        filled = sum(1 for f in self.fields.values() if raw_data.get(f.id))
        return (filled / total) * 100 if total > 0 else 0
    
    def can_advance_from_step(self, step_id, raw_data):
        return len(self.get_missing_mandatory_fields(step_id, raw_data)) == 0


def build_test_session_context(session, form_manager):
    """Build session context untuk testing"""
    current_step_id = session.current_step
    current_step_obj = form_manager.get_step(current_step_id)
    
    current_fields = form_manager.get_fields_for_step(current_step_id)
    missing_fields = form_manager.get_missing_mandatory_fields(current_step_id, session.raw_data)
    completion = form_manager.calculate_completion(session.raw_data)
    
    return {
        "session_id": session.session_id,
        "current_step": {
            "id": current_step_id,
            "name": current_step_obj.name if current_step_obj else "",
            "description": current_step_obj.description if current_step_obj else "",
            "icon": "📝",
            "index": form_manager.get_step_index(current_step_id),
            "total_steps": len(form_manager.get_steps())
        },
        "collected_data": {
            k: v for k, v in session.raw_data.items() 
            if not k.startswith("_")
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
        "recent_messages": session.get_recent_messages(5),
        "validation_errors": session.validation_errors,
        "can_advance": form_manager.can_advance_from_step(current_step_id, session.raw_data),
        "registration_number": session.registration_number
    }


# =============================================================================
# TEST CASES
# =============================================================================

async def test_contextual_processing():
    """Test contextual message processing"""
    
    print("=" * 60)
    print("🧪 TEST CONTEXTUAL UNDERSTANDING")
    print("=" * 60)
    
    # Check API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY tidak ditemukan!")
        print("   Set environment variable: export OPENAI_API_KEY=sk-...")
        return
    
    # Import LLM client
    from openai import AsyncOpenAI
    
    client = AsyncOpenAI(api_key=api_key)
    
    # Create mock objects
    session = MockSession()
    form_manager = MockFormManager()
    
    # Build session context
    session_context = build_test_session_context(session, form_manager)
    
    # Get fields for current step
    fields = form_manager.get_fields_for_step(session.current_step)
    fields_dict = [
        {
            "id": f.id,
            "label": f.label,
            "type": f.type,
            "examples": f.examples,
            "is_mandatory": f.is_mandatory
        }
        for f in fields
    ]
    
    # Build context prompt
    def build_context_prompt(ctx):
        current_step = ctx.get("current_step", {})
        collected_data = ctx.get("collected_data", {})
        missing_fields = ctx.get("missing_fields", [])
        completion = ctx.get("completion_percentage", 0)
        
        collected_str = "\n".join([f"  - {k}: {v}" for k, v in collected_data.items() if not k.startswith("_")]) or "  (belum ada)"
        missing_str = "\n".join([f"  - {f.get('label')}" for f in missing_fields[:5]]) or "  (lengkap)"
        
        return f"""
=== KONTEKS SESI ===
📍 TAHAP: {current_step.get('name', 'Unknown')}
📊 PROGRESS: {completion:.0f}%

📝 DATA TERKUMPUL:
{collected_str}

❗ DATA DIPERLUKAN:
{missing_str}
"""
    
    context_prompt = build_context_prompt(session_context)
    field_desc = "\n".join([f"- {f['id']}: {f['label']} ({f['type']})" for f in fields_dict])
    
    # Test cases
    test_messages = [
        ("halo", "greeting"),
        ("apa saja yang perlu diisi?", "question"),
        ("maksudnya gimana sih?", "clarification"),
        ("lahir di Bandung tanggal 15 Mei 2010", "data_input"),
        ("lanjut ke tahap berikutnya", "command"),
        ("saya perempuan", "data_input"),
        ("asdfghjkl", "unknown/clarification"),
    ]
    
    system_prompt = f"""Kamu AI asisten pendaftaran sekolah.

{context_prompt}

FIELD DI TAHAP INI:
{field_desc}

INTENT:
- "data_input": User beri data
- "question": User bertanya
- "command": User perintah (lanjut/kembali/summary/help)
- "clarification": User bingung
- "greeting": User sapa

RESPOND JSON:
{{"intent": "...", "extracted_fields": {{}}, "suggested_response": "...", "confidence": 0.0-1.0}}"""

    print(f"\n📋 Session Context:")
    print(context_prompt)
    
    for msg, expected_intent in test_messages:
        print(f"\n{'─' * 50}")
        print(f"📨 Input: \"{msg}\"")
        print(f"   Expected: {expected_intent}")
        
        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f'PESAN: "{msg}"'}
                ],
                temperature=0.2,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content
            import json
            result = json.loads(result_text)
            
            intent = result.get("intent", "unknown")
            extracted = result.get("extracted_fields", {})
            suggested = result.get("suggested_response", "")[:100]
            confidence = result.get("confidence", 0)
            
            status = "✅" if intent == expected_intent or (expected_intent == "unknown/clarification" and intent in ["clarification", "data_input"]) else "⚠️"
            
            print(f"   {status} Result: intent={intent}, confidence={confidence:.2f}")
            if extracted:
                print(f"   📦 Extracted: {extracted}")
            if suggested:
                print(f"   💬 Response: {suggested}...")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print(f"\n{'=' * 60}")
    print("✅ Test complete!")


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    print("\n🚀 Running Contextual Understanding Tests...\n")
    asyncio.run(test_contextual_processing())