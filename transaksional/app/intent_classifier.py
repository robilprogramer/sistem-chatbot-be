"""
Intent Classifier
=================
Mengklasifikasikan intent user message:
- INFORMATIONAL: Pertanyaan umum yang perlu dijawab oleh RAG
- TRANSACTIONAL: Input data untuk pendaftaran
- COMMAND: Perintah sistem (lanjut, kembali, konfirmasi, dll)
"""

from typing import Tuple, List, Optional
from enum import Enum
import re

from transaksional.app.llm_client import get_llm


class UserIntent(str, Enum):
    """Intent dari pesan user"""
    INFORMATIONAL = "informational"  # Pertanyaan umum -> RAG
    TRANSACTIONAL = "transactional"  # Input data pendaftaran
    COMMAND = "command"              # Perintah sistem
    HYBRID = "hybrid"                # Pertanyaan + data (need special handling)


class IntentClassifier:
    """
    Classifier untuk menentukan intent dari pesan user.
    
    Menggunakan kombinasi:
    1. Rule-based untuk deteksi cepat
    2. LLM untuk kasus ambigu
    """
    
    # Pattern pertanyaan informational - EXPANDED
    QUESTION_PATTERNS = [
        # === KATA TANYA DASAR ===
        r'\b(apa\s+(?:saja|itu|yang|ada)?)\b',
        r'\b(berapa\s+(?:biaya|harga|lama|banyak|tahun|bulan|hari|orang|kelas)?)\b', 
        r'\b(bagaimana\s+(?:cara|caranya|kalau|dengan|sistem|proses)?)\b',
        r'\b(kapan\s+(?:batas|deadline|mulai|buka|tutup|selesai|dimulai)?)\b',
        r'\b(dimana|di\s*mana|lokasi\s*(?:nya)?)\b',
        r'\b(siapa\s+(?:yang|saja|nama)?)\b',
        r'\b(mengapa|kenapa)\b',
        r'\b(apakah|bisakah|bolehkah|dapatkah|mungkinkah)\b',
        r'\b(gimana|gmn|gmna)\b',  # Slang
        r'\b(brp|brapa)\b',  # Slang berapa
        
        # === TANDA TANYA ===
        r'\?$',
        r'\?\s*$',
        
        # === KATA KERJA BERTANYA ===
        r'\b(tolong\s+(?:jelaskan|kasih\s+tau|info|beritahu|sebutkan))\b',
        r'\b(mau\s+(?:tanya|nanya|tau|tahu|bertanya))\b',
        r'\b(bisa\s+(?:dijelaskan|dijelasin|kasih\s+info|tolong|minta))\b',
        r'\b(boleh\s+(?:tanya|nanya|tau|tahu|minta))\b',
        r'\b(minta\s+(?:info|informasi|penjelasan|detail))\b',
        r'\b(kasih\s+(?:tau|tahu|info))\b',
        r'\b(jelasin|jelaskan)\b',
        
        # === TOPIK INFORMASI SEKOLAH ===
        # Biaya & Pembayaran
        r'\b(biaya(?:nya)?(?:\s+(?:berapa|pendaftaran|sekolah|masuk|spp|bulanan|tahunan|total))?)\b',
        r'\b(harga|tarif|bayar|pembayaran|cicilan|angsuran)\b',
        r'\b(spp|uang\s+(?:gedung|pangkal|sekolah|masuk|pendaftaran))\b',
        r'\b(gratis|diskon|potongan|keringanan)\b',
        
        # Program & Kurikulum
        r'\b(program\s*(?:nya|apa|yang|unggulan|khusus)?)\b',
        r'\b(kurikulum(?:nya)?(?:\s+(?:apa|yang))?)\b',
        r'\b(mata\s*pelajaran|mapel|pelajaran)\b',
        r'\b(kelas\s*(?:unggulan|reguler|khusus|bilingual|internasional))\b',
        r'\b(jurusan|peminatan|konsentrasi)\b',
        
        # Ekstrakurikuler & Fasilitas
        r'\b(ekstrakurikuler|ekskul|ekstra)\b',
        r'\b(fasilitas(?:nya)?(?:\s+(?:apa|yang))?)\b',
        r'\b(kegiatan(?:\s+(?:apa|yang|siswa|sekolah))?)\b',
        r'\b(lab|laboratorium|perpustakaan|lapangan|masjid|kantin)\b',
        r'\b(olahraga|seni|musik|robotik|pramuka|pmr)\b',
        
        # Jadwal & Waktu
        r'\b(jadwal(?:nya)?(?:\s+(?:pendaftaran|masuk|belajar|sekolah))?)\b',
        r'\b(jam\s*(?:belajar|sekolah|masuk|pulang|operasional))\b',
        r'\b(waktu\s*(?:pendaftaran|belajar|buka|tutup))\b',
        r'\b(kapan\s*(?:buka|tutup|mulai|selesai|deadline))\b',
        r'\b(tanggal\s*(?:penting|pendaftaran|tes|ujian))\b',
        r'\b(periode|gelombang|batch|tahap)\b',
        
        # Syarat & Persyaratan
        r'\b(syarat(?:\s*-?\s*syarat)?(?:nya)?)\b',
        r'\b(persyaratan(?:nya)?)\b',
        r'\b(ketentuan|kriteria|kualifikasi)\b',
        r'\b(dokumen\s*(?:apa|yang|diperlukan|dibutuhkan))\b',
        r'\b(berkas|file|lampiran)\b',
        r'\b(usia\s*(?:minimal|maksimal|minimum|maximum))\b',
        r'\b(umur\s*(?:berapa|minimal|maksimal))\b',
        
        # Lokasi & Kontak
        r'\b(lokasi|alamat|tempat)\s*(?:sekolah|kampus|nya)?\b',
        r'\b(dimana|di\s*mana)\s*(?:letak|lokasi|alamat)?\b',
        r'\b(kontak|hubungi|telepon|telp|hp|wa|whatsapp)\b',
        r'\b(email|website|web|sosmed|instagram|ig)\b',
        r'\b(cara\s*(?:ke|menuju|kesana|daftar))\b',
        
        # Akreditasi & Prestasi
        r'\b(akreditasi(?:nya)?)\b',
        r'\b(peringkat|ranking|rangking)\b',
        r'\b(prestasi|penghargaan|achievement)\b',
        r'\b(lulusan|alumni|output)\b',
        r'\b(kualitas|mutu)\b',
        
        # Beasiswa & Bantuan
        r'\b(beasiswa(?:nya)?(?:\s+(?:apa|ada))?)\b',
        r'\b(bantuan\s*(?:biaya|keuangan|finansial))\b',
        r'\b(kip|pip|bos)\b',  # Program bantuan pemerintah
        
        # Seragam & Perlengkapan
        r'\b(seragam(?:nya)?(?:\s+(?:apa|berapa|seperti))?)\b',
        r'\b(buku|alat\s*tulis|perlengkapan)\b',
        
        # Guru & Tenaga Pendidik
        r'\b(guru(?:nya)?(?:\s+(?:siapa|berapa|bagaimana))?)\b',
        r'\b(pengajar|pendidik|ustadz|ustadzah)\b',
        r'\b(tenaga\s*(?:pengajar|pendidik|ahli))\b',
        
        # Proses Pendaftaran
        r'\b(cara\s*(?:daftar|mendaftar|pendaftaran))\b',
        r'\b(proses\s*(?:pendaftaran|seleksi|penerimaan))\b',
        r'\b(tahapan|langkah|step|alur)\b',
        r'\b(tes\s*(?:masuk|seleksi|ujian|tulis|wawancara))\b',
        r'\b(seleksi|ujian\s*masuk)\b',
        
        # Jenjang Pendidikan
        r'\b(jenjang(?:\s+(?:apa|yang|tersedia))?)\b',
        r'\b(tingkat(?:an)?(?:\s+(?:apa|yang))?)\b',
        r'\b(tk|paud|playgroup|sd|mi|smp|mts|sma|ma|smk)\b',
        
        # Info Umum
        r'\b(info(?:rmasi)?(?:\s+(?:tentang|mengenai|soal|lengkap))?)\b',
        r'\b(detail(?:nya)?(?:\s+(?:tentang|mengenai))?)\b',
        r'\b(penjelasan|keterangan)\b',
        r'\b(ceritakan|jelaskan|sebutkan)\s+(?:tentang)?\b',
        
        # Perbandingan
        r'\b(beda(?:nya)?|perbedaan|berbeda)\b',
        r'\b(sama|persamaan|mirip)\b',
        r'\b(lebih\s*(?:baik|bagus|unggul))\b',
        r'\b(keunggulan|kelebihan|keuntungan)\b',
        r'\b(kekurangan|kelemahan)\b',
    ]
    
    # Pattern command sistem
    COMMAND_PATTERNS = {
        "advance": [r'\b(lanjut|next|terus|ok|oke|okey|lanjutkan)\b'],
        "back": [r'\b(kembali|back|mundur|sebelumnya)\b'],
        "confirm": [r'\b(konfirmasi|confirm|kirim|submit|setuju|ya)\b'],
        "summary": [r'\b(summary|ringkasan|lihat\s+data|cek\s+data)\b'],
        "reset": [r'\b(reset|ulang|mulai\s+(?:dari\s+)?awal|batal)\b'],
        "help": [r'\b(help|bantuan|bantu|tolong)\b'],
        "skip": [r'\b(skip|lewat|lewati)\b'],
    }
    
    # Pattern yang menandakan ada data di pesan
    DATA_INDICATORS = [
        # Personal data patterns
        r'\b(?:nama\s+(?:saya|anak|siswa)?\s*(?:adalah|:)?\s*)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b',  # Nama orang
        r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b',  # Tanggal
        r'\b(?:08|62)\d{8,12}\b',  # Nomor telepon
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
        r'\bjl\.?\s+\w+|jalan\s+\w+\b',  # Alamat (Jl.)
        r'\b(?:laki|perempuan|pria|wanita|cowo|cewe|cowok|cewek)\b',  # Gender
        r'\brt\s*\d+\s*/?\s*rw\s*\d+\b',  # RT/RW
        r'\b\d{5}\b',  # Kode pos
        r'\b(?:sd|smp|sma|smk|tk|paud)\s+\w+\b',  # Nama sekolah
        r'\bnisn\s*:?\s*\d+\b',  # NISN
    ]
    
    def __init__(self):
        self.llm = None  # Lazy load
        
    def _compile_patterns(self, patterns: List[str]) -> List[re.Pattern]:
        """Compile regex patterns"""
        return [re.compile(p, re.IGNORECASE) for p in patterns]
    
    def _check_question_patterns(self, message: str) -> bool:
        """Check apakah pesan mengandung pola pertanyaan"""
        message_lower = message.lower()
        for pattern in self.QUESTION_PATTERNS:
            if re.search(pattern, message_lower):
                return True
        return False
    
    def _check_command_patterns(self, message: str) -> Tuple[bool, Optional[str]]:
        """Check apakah pesan adalah command"""
        message_lower = message.lower().strip()
        
        # Check exact match first
        for command, patterns in self.COMMAND_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    # Make sure it's primarily a command (short message)
                    if len(message_lower.split()) <= 3:
                        return True, command
        return False, None
    
    def _check_data_indicators(self, message: str) -> bool:
        """Check apakah pesan mengandung data"""
        for pattern in self.DATA_INDICATORS:
            if re.search(pattern, message, re.IGNORECASE):
                return True
        return False
    
    def _has_name_pattern(self, message: str) -> bool:
        """Check if message contains name-like pattern"""
        # Pattern untuk nama: "nama saya X" atau "saya X" atau just proper names
        name_patterns = [
            r'nama\s+(?:saya|anak|siswa|lengkap)?\s*(?:adalah|:)?\s*\w+',
            r'saya\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*',
        ]
        for pattern in name_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True
        return False
    
    def classify_fast(self, message: str) -> Tuple[UserIntent, float, Optional[str]]:
        """
        Klasifikasi cepat menggunakan rules.
        
        Returns:
            Tuple of (intent, confidence, command_type)
        """
        message = message.strip()
        
        # 1. Check command first (highest priority for short messages)
        is_command, command_type = self._check_command_patterns(message)
        if is_command:
            return UserIntent.COMMAND, 0.95, command_type
        
        # 2. Check question patterns
        is_question = self._check_question_patterns(message)
        
        # 3. Check data indicators
        has_data = self._check_data_indicators(message) or self._has_name_pattern(message)
        
        # 4. Decide intent
        if is_question and has_data:
            # Hybrid case - ada pertanyaan tapi juga ada data
            # E.g., "nama saya Ahmad, program apa saja yang ada?"
            return UserIntent.HYBRID, 0.7, None
        elif is_question:
            return UserIntent.INFORMATIONAL, 0.85, None
        elif has_data:
            return UserIntent.TRANSACTIONAL, 0.85, None
        else:
            # Ambiguous - likely transactional (default for registration flow)
            return UserIntent.TRANSACTIONAL, 0.5, None
    
    async def classify_with_llm(self, message: str, context: str = "") -> Tuple[UserIntent, float]:
        """
        Klasifikasi menggunakan LLM untuk kasus ambigu.
        
        Args:
            message: Pesan user
            context: Context dari conversation sebelumnya
            
        Returns:
            Tuple of (intent, confidence)
        """
        if self.llm is None:
            self.llm = get_llm()
        
        system_prompt = """Kamu adalah classifier yang menentukan intent dari pesan user dalam konteks pendaftaran sekolah.

Intent yang mungkin:
1. INFORMATIONAL - User bertanya informasi umum tentang sekolah/pendaftaran
   Contoh: "apa saja programnya?", "berapa biayanya?", "syarat pendaftaran apa?"

2. TRANSACTIONAL - User memberikan data untuk proses pendaftaran
   Contoh: "nama saya Ahmad", "lahir di Jakarta", "email saya@test.com"

3. COMMAND - User memberi perintah navigasi
   Contoh: "lanjut", "kembali", "konfirmasi", "reset"

4. HYBRID - Pesan mengandung pertanyaan DAN data
   Contoh: "nama saya Ahmad, btw program apa saja?"

Respond dengan JSON: {"intent": "...", "confidence": 0.0-1.0}"""

        user_prompt = f"""Context: {context}

Pesan user: "{message}"

Tentukan intent:"""

        try:
            response = await self.llm.generate(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                json_mode=True
            )
            
            import json
            result = json.loads(response)
            intent_str = result.get("intent", "transactional").lower()
            confidence = float(result.get("confidence", 0.7))
            
            intent_map = {
                "informational": UserIntent.INFORMATIONAL,
                "transactional": UserIntent.TRANSACTIONAL,
                "command": UserIntent.COMMAND,
                "hybrid": UserIntent.HYBRID,
            }
            
            return intent_map.get(intent_str, UserIntent.TRANSACTIONAL), confidence
            
        except Exception as e:
            print(f"LLM classification error: {e}")
            # Fallback to fast classification
            intent, conf, _ = self.classify_fast(message)
            return intent, conf * 0.7  # Lower confidence for fallback
    
    async def classify(
        self, 
        message: str, 
        context: str = "",
        use_llm_threshold: float = 0.6
    ) -> Tuple[UserIntent, float, Optional[str]]:
        """
        Main classification method.
        
        Args:
            message: Pesan user
            context: Context conversation
            use_llm_threshold: Jika confidence < threshold, gunakan LLM
            
        Returns:
            Tuple of (intent, confidence, command_type)
        """
        # Fast classification first
        intent, confidence, command_type = self.classify_fast(message)
        
        # If confident enough or it's a command, return immediately
        if confidence >= use_llm_threshold or intent == UserIntent.COMMAND:
            return intent, confidence, command_type
        
        # Use LLM for ambiguous cases
        try:
            llm_intent, llm_confidence = await self.classify_with_llm(message, context)
            
            # Use LLM result if more confident
            if llm_confidence > confidence:
                return llm_intent, llm_confidence, None
        except:
            pass
        
        return intent, confidence, command_type


# Singleton instance
_classifier: Optional[IntentClassifier] = None


def get_intent_classifier() -> IntentClassifier:
    """Get singleton classifier"""
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier


# Convenience function
async def classify_intent(message: str, context: str = "") -> Tuple[UserIntent, float, Optional[str]]:
    """
    Classify intent dari pesan user.
    
    Args:
        message: Pesan user
        context: Context conversation
        
    Returns:
        Tuple of (intent, confidence, command_type)
    """
    classifier = get_intent_classifier()
    return await classifier.classify(message, context)
