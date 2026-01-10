# services/pdf_to_knowledge_markdown.py

import os
import time
import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from openai import OpenAI
import fitz  # PyMuPDF

@dataclass
class KnowledgeResult:
    """Result from PDF to Knowledge conversion"""
    knowledge_text: str
    total_pages: int
    has_tables: bool
    ai_model: str
    original_length: int
    knowledge_length: int
    processing_duration: float
    metadata: Dict
    doc_type: str


class PDFToKnowledgeMarkdownConverter:
    """
    Convert PDF to structured markdown knowledge base
    Optimized for RAG retrieval with metadata extraction
    
    Supports multiple document types:
    - FAQ: Question-answer format
    - BIAYA: Pricing/fee information
    - PERATURAN: Regulations/policies
    - GENERAL: Other documents
    """
    
    def __init__(
        self,
        openai_api_key: str,
        model: str = "gpt-4o-mini",
        temperature: float = 0.3
    ):
        self.client = OpenAI(api_key=openai_api_key)
        self.model = model
        self.temperature = temperature
    
    def process(
        self,
        pdf_path: str,
        doc_title: str = "Dokumen",
        doc_type: str = "AUTO"  # AUTO, FAQ, BIAYA, PERATURAN, GENERAL
    ) -> KnowledgeResult:
        """
        Main processing function
        
        Args:
            pdf_path: Path to PDF file
            doc_title: Document title
            doc_type: Document type (AUTO for auto-detection)
            
        Returns:
            KnowledgeResult with structured markdown
        """
        start_time = time.time()
        
        print(f"📄 Processing: {pdf_path}")
        
        # Extract text from PDF
        raw_text, total_pages, has_tables = self._extract_pdf_text(pdf_path)
        
        print(f"✅ Extracted {len(raw_text)} chars from {total_pages} pages")
        
        # Auto-detect document type if not specified
        if doc_type == "AUTO":
            doc_type = self._detect_document_type(raw_text, doc_title)
            print(f"🔍 Detected document type: {doc_type}")
        
        # Convert to structured markdown based on type
        print(f"🔄 Converting to markdown (type: {doc_type})...")
        
        if doc_type == "FAQ":
            knowledge_text = self._convert_faq_to_markdown(raw_text, doc_title)
        elif doc_type == "BIAYA":
            knowledge_text = self._convert_biaya_to_markdown(raw_text, doc_title)
        elif doc_type == "PERATURAN":
            knowledge_text = self._convert_peraturan_to_markdown(raw_text, doc_title)
        else:
            knowledge_text = self._convert_general_to_markdown(raw_text, doc_title)
        
        # Extract metadata
        metadata = self._extract_metadata(knowledge_text, doc_title)
        
        processing_duration = time.time() - start_time
        
        print(f"✅ Conversion completed in {processing_duration:.2f}s")
        print(f"📊 Output: {len(knowledge_text)} chars")
        
        return KnowledgeResult(
            knowledge_text=knowledge_text,
            total_pages=total_pages,
            has_tables=has_tables,
            ai_model=self.model,
            original_length=len(raw_text),
            knowledge_length=len(knowledge_text),
            processing_duration=processing_duration,
            metadata=metadata,
            doc_type=doc_type
        )
    
    def _extract_pdf_text_old(self, pdf_path: str) -> Tuple[str, int, bool]:
        """
        Extract text from PDF using PyMuPDF
        
        Returns:
            Tuple of (text, page_count, has_tables)
        """
        doc = fitz.open(pdf_path)
        full_text = []
        has_tables = False
        
        for page_num, page in enumerate(doc, 1):
            text = page.get_text()
            full_text.append(text)
            
            # Simple table detection
            if "|" in text or "─" in text or "\t" in text:
                has_tables = True
        
        doc.close()
        
        return "\n\n".join(full_text), len(doc), has_tables
    
    def _extract_pdf_text(self, pdf_path: str) -> Tuple[str, int, bool]:
        doc = fitz.open(pdf_path)
        full_text = []
        has_tables = False
        
        # ✅ Store page count SEBELUM closing
        page_count = len(doc)
        
        for page_num, page in enumerate(doc, 1):
            text = page.get_text()
            full_text.append(text)
            
            if "|" in text or "─" in text or "\t" in text:
                has_tables = True
        
        doc.close()
        
        return "\n\n".join(full_text), page_count, has_tables  # ✅ Gunakan stored value
    
    def _detect_document_type(self, text: str, title: str) -> str:
        """
        Auto-detect document type based on content and title
        """
        text_lower = text.lower()
        title_lower = title.lower()
        
        # Check for FAQ indicators
        faq_keywords = [
            "pertanyaan", "jawaban", "bagaimana cara", 
            "q:", "a:", "faq", "tanya jawab"
        ]
        faq_count = sum(1 for kw in faq_keywords if kw in text_lower or kw in title_lower)
        
        # Check for pricing indicators
        biaya_keywords = [
            "biaya", "rp", "rupiah", "tarif", "spp", 
            "uang pangkal", "iuran", "pembayaran"
        ]
        biaya_count = sum(1 for kw in biaya_keywords if kw in text_lower or kw in title_lower)
        
        # Check for regulation indicators
        peraturan_keywords = [
            "peraturan", "sk", "keputusan", "ketentuan", 
            "pasal", "ayat", "nomor"
        ]
        peraturan_count = sum(1 for kw in peraturan_keywords if kw in text_lower or kw in title_lower)
        
        # Determine type based on highest count
        counts = {
            "FAQ": faq_count,
            "BIAYA": biaya_count,
            "PERATURAN": peraturan_count
        }
        
        max_type = max(counts, key=counts.get)
        
        # If no clear winner, default to GENERAL
        if counts[max_type] < 2:
            return "GENERAL"
        
        return max_type
    
    def _convert_faq_to_markdown(self, raw_text: str, doc_title: str) -> str:
        """
        Convert FAQ document to structured markdown
        Following the format from CS.pdf example
        """
        system_prompt = """Anda adalah AI expert yang mengkonversi dokumen FAQ menjadi knowledge base terstruktur dalam format Markdown.

TUGAS ANDA:
1. Identifikasi setiap pasangan pertanyaan-jawaban dalam dokumen
2. Kelompokkan berdasarkan kategori yang relevan (misal: PENDAFTARAN AKUN, PEMBAYARAN, TROUBLESHOOTING, dll)
3. Format setiap FAQ dengan struktur yang konsisten
4. Extract keywords untuk setiap FAQ
5. Pastikan informasi lengkap, detail, dan mudah dicari

FORMAT OUTPUT (WAJIB DIIKUTI):
```markdown
# Knowledge Base - [Judul Dokumen]

## KATEGORI: [NAMA KATEGORI UPPERCASE]

### FAQ [Number]: [Judul Singkat Deskriptif]

**Pertanyaan:** [Pertanyaan lengkap dalam bentuk kalimat tanya]

**Jawaban:**

[Jawaban lengkap dengan formatting yang jelas]

**Untuk langkah-langkah, gunakan format:**
**Langkah 1: [Nama Langkah]**
- [Detail langkah]
- [Sub-detail jika ada]

**Langkah 2: [Nama Langkah]**
- [Detail langkah]

**Catatan Penting:**
- [Catatan 1]
- [Catatan 2]

**Keywords:** [keyword1, keyword2, keyword3, keyword4]

---

### FAQ [Number+1]: ...
```

ATURAN PENTING:
1. Setiap FAQ harus punya struktur: Pertanyaan, Jawaban, Keywords
2. Jawaban harus SANGAT detail dan mudah dipahami - jangan potong informasi
3. Kelompokkan FAQ dengan tema serupa dalam satu kategori
4. Keywords harus mencakup semua istilah yang mungkin dicari user
5. Gunakan **bold** untuk poin penting
6. Gunakan bullet points (-) untuk daftar item
7. Gunakan numbered list untuk prosedur berurutan
8. Pertahankan SEMUA informasi penting dari dokumen asli
9. Jika ada link, nomor telepon, atau informasi kontak - SERTAKAN
10. Format nomor, tanggal, dan informasi teknis dengan jelas

CONTOH KEYWORDS YANG BAIK:
- Untuk FAQ tentang pendaftaran: "pendaftaran akun, registrasi, OTP, verifikasi, nomor HP, email"
- Untuk FAQ tentang pembayaran: "pembayaran, virtual account, VA, bank transfer, SPP, tagihan"
- Untuk FAQ troubleshooting: "error, gagal bayar, tidak bisa login, lupa PIN, reset password"
"""

        user_prompt = f"""Konversi dokumen FAQ berikut menjadi knowledge base terstruktur yang SANGAT detail dan comprehensive:

DOKUMEN: {doc_title}

KONTEN:
{raw_text}

INSTRUKSI KHUSUS:
- Buat kategori yang logis dan mudah dipahami
- Setiap FAQ harus standalone (bisa dipahami tanpa membaca FAQ lain)
- Jangan hilangkan informasi detail
- Pastikan semua langkah-langkah dijelaskan dengan jelas
- Sertakan semua link, kontak, dan informasi penting

Hasilkan knowledge base dalam format markdown yang telah ditentukan."""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=self.temperature,
            max_tokens=16000
        )
        
        return response.choices[0].message.content
    
    def _convert_biaya_to_markdown(self, raw_text: str, doc_title: str) -> str:
        """
        Convert pricing document to structured markdown
        """
        system_prompt = """Anda adalah AI expert yang mengkonversi dokumen biaya/tarif menjadi knowledge base terstruktur.

TUGAS ANDA:
1. Identifikasi semua komponen biaya dalam dokumen
2. Kelompokkan biaya berdasarkan jenjang, program, atau kategori
3. Extract informasi periode berlaku, cara pembayaran, kebijakan cicilan
4. Buat tabel yang mudah dibaca untuk komponen biaya
5. Tambahkan penjelasan untuk setiap komponen biaya

FORMAT OUTPUT:
```markdown
# Knowledge Base - [Judul Dokumen Biaya]

## METADATA DOKUMEN
- **Jenjang**: [TK/SD/SMP/SMA/SMK]
- **Cabang**: [Nama Cabang]
- **Tahun Ajaran**: [YYYY/YYYY]
- **Periode Berlaku**: [Tanggal - Tanggal]
- **Terakhir Diupdate**: [Tanggal]

## RINGKASAN BIAYA

[Penjelasan umum tentang struktur biaya sekolah]

## RINCIAN BIAYA

### Biaya [Kategori 1] - [Nama Program]

**Komponen Biaya:**

| Komponen | Jumlah | Keterangan |
|----------|--------|------------|
| Uang Pangkal | Rp XXX.XXX | [Detail] |
| SPP per Bulan | Rp XXX.XXX | [Detail] |
| [Komponen lain] | Rp XXX.XXX | [Detail] |

**Total Biaya:** Rp XXX.XXX.XXX

**Cara Pembayaran:**
- **Virtual Account**: [Bank-bank yang tersedia]
- **Transfer**: [Detail rekening]
- **Tunai**: [Lokasi dan jam]

**Kebijakan Cicilan:**
- [Detail kebijakan cicilan jika ada]
- [Syarat dan ketentuan]

**Diskon & Beasiswa:**
- [Program diskon jika ada]
- [Informasi beasiswa]

**Catatan Penting:**
- [Catatan 1]
- [Catatan 2]

**Keywords:** [biaya, spp, uang pangkal, jenjang, cabang]

---
```

ATURAN:
1. Semua nominal harus AKURAT dan jelas formatnya (Rp X.XXX.XXX)
2. Grouping berdasarkan jenjang dan program jika ada perbedaan
3. WAJIB sertakan informasi periode berlaku
4. Jelaskan DETAIL cara pembayaran dan metode yang tersedia
5. Highlight kebijakan penting (diskon, beasiswa, denda keterlambatan)
6. Sertakan kontak untuk informasi lebih lanjut
7. Gunakan tabel untuk informasi biaya agar mudah dibaca
"""

        user_prompt = f"""Konversi dokumen biaya berikut menjadi knowledge base terstruktur:

DOKUMEN: {doc_title}

KONTEN:
{raw_text}

INSTRUKSI:
- Extract SEMUA komponen biaya dengan akurat
- Format nominal dengan jelas (gunakan titik sebagai pemisah ribuan)
- Kelompokkan berdasarkan jenjang/program jika ada perbedaan
- Sertakan semua informasi pembayaran

Hasilkan knowledge base dalam format markdown yang telah ditentukan."""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=self.temperature,
            max_tokens=16000
        )
        
        return response.choices[0].message.content
    
    def _convert_peraturan_to_markdown(self, raw_text: str, doc_title: str) -> str:
        """
        Convert regulation document to structured markdown
        """
        system_prompt = """Anda adalah AI expert yang mengkonversi dokumen peraturan/SK menjadi knowledge base terstruktur.

TUGAS ANDA:
1. Identifikasi struktur peraturan (pasal, ayat, poin)
2. Extract informasi kunci (nomor SK, tanggal, tentang apa)
3. Susun dalam format yang mudah dicari dan dipahami
4. Tambahkan ringkasan untuk setiap pasal/bagian penting
5. Jelaskan implikasi praktis dari peraturan

FORMAT OUTPUT:
```markdown
# Knowledge Base - [Nomor dan Judul Peraturan]

## INFORMASI DOKUMEN
- **Nomor**: [Nomor SK/Peraturan]
- **Tanggal Penetapan**: [Tanggal]
- **Tentang**: [Judul Lengkap]
- **Ditetapkan oleh**: [Pihak yang menetapkan]
- **Berlaku sejak**: [Tanggal]
- **Status**: [Aktif/Dicabut/Direvisi]

## RINGKASAN EKSEKUTIF

[Ringkasan singkat isi peraturan dalam 2-3 paragraf]

**Poin Utama:**
- [Poin penting 1]
- [Poin penting 2]
- [Poin penting 3]

## ISI PERATURAN

### Pasal [X]: [Judul Pasal]

**Ringkasan:** [Penjelasan singkat pasal ini dalam bahasa awam]

**Isi Lengkap:**
1. [Ayat 1 - dengan penjelasan]
2. [Ayat 2 - dengan penjelasan]

**Implikasi Praktis:** 
[Apa artinya untuk siswa/orang tua/guru - dalam bahasa yang mudah dipahami]

**Contoh Penerapan:**
[Jika relevan, berikan contoh konkret]

---

### Pasal [X+1]: ...

## KETENTUAN PERALIHAN

[Jika ada ketentuan peralihan]

## KETENTUAN PENUTUP

[Jika ada ketentuan penutup]

## FAQ TERKAIT PERATURAN

### Pertanyaan Umum 1:
**Q:** [Pertanyaan yang mungkin muncul]
**A:** [Jawaban berdasarkan peraturan]

**Keywords:** [peraturan, sk, nomor sk, pasal, ketentuan]
```

ATURAN:
1. Pertahankan struktur hukum (Pasal, Ayat, Poin) dengan akurat
2. WAJIB sertakan ringkasan untuk kemudahan pemahaman
3. Jelaskan implikasi praktis dari setiap pasal penting
4. Extract tanggal dan nomor dengan AKURAT
5. Gunakan bahasa yang mudah dipahami awam (tidak terlalu legal/formal)
6. Tambahkan FAQ untuk pertanyaan umum tentang peraturan
"""

        user_prompt = f"""Konversi dokumen peraturan berikut menjadi knowledge base terstruktur:

DOKUMEN: {doc_title}

KONTEN:
{raw_text}

INSTRUKSI:
- Extract nomor SK, tanggal, dan informasi meta dengan akurat
- Jelaskan setiap pasal dengan bahasa yang mudah dipahami
- Sertakan implikasi praktis
- Buat FAQ untuk pertanyaan umum

Hasilkan knowledge base dalam format markdown yang telah ditentukan."""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=self.temperature,
            max_tokens=16000
        )
        
        return response.choices[0].message.content
    
    def _convert_general_to_markdown(self, raw_text: str, doc_title: str) -> str:
        """
        Convert general document to structured markdown
        """
        system_prompt = """Anda adalah AI expert yang mengkonversi dokumen menjadi knowledge base terstruktur.

TUGAS ANDA:
1. Identifikasi topik utama dalam dokumen
2. Kelompokkan informasi berdasarkan topik/tema
3. Buat struktur hierarki yang logis
4. Extract dan highlight poin-poin penting

FORMAT OUTPUT:
```markdown
# Knowledge Base - [Judul Dokumen]

## OVERVIEW

[Ringkasan dokumen - apa yang dibahas, untuk siapa, tujuannya apa]

## TOPIK 1: [Nama Topik]

### Sub-topik 1.1: [Nama Sub-topik]

[Konten detail dengan penjelasan lengkap]

**Poin Penting:**
- [Poin 1]
- [Poin 2]

**Contoh/Ilustrasi:**
[Jika ada contoh yang membantu pemahaman]

---

### Sub-topik 1.2: ...

## TOPIK 2: [Nama Topik]

...

## RINGKASAN DAN KESIMPULAN

[Ringkasan seluruh dokumen]

**Keywords:** [keyword1, keyword2, keyword3]
```

ATURAN:
1. Struktur harus logis dan mudah dinavigasi
2. Setiap section harus standalone (bisa dipahami sendiri)
3. Gunakan formatting untuk clarity (bold, lists, dll)
4. Sertakan contoh jika membantu pemahaman
5. Highlight informasi penting dengan **bold**
"""

        user_prompt = f"""Konversi dokumen berikut menjadi knowledge base terstruktur:

DOKUMEN: {doc_title}

KONTEN:
{raw_text}

INSTRUKSI:
- Buat struktur yang logis berdasarkan konten
- Kelompokkan informasi berdasarkan tema
- Sertakan ringkasan di awal dan akhir

Hasilkan knowledge base dalam format markdown yang telah ditentukan."""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=self.temperature,
            max_tokens=16000
        )
        
        return response.choices[0].message.content
    
    def _extract_metadata(self, knowledge_text: str, doc_title: str) -> Dict:
        """
        Extract metadata from generated knowledge base
        """
        metadata = {
            "jenjang": None,
            "cabang": None,
            "tahun": None,
            "kategori": None,
            "doc_type": None
        }
        
        text_lower = knowledge_text.lower()
        title_lower = doc_title.lower()
        combined = text_lower + " " + title_lower
        
        # Extract jenjang
        jenjang_list = ["TK", "SD", "SMP", "SMA", "SMK"]
        for j in jenjang_list:
            if re.search(rf'\b{j.lower()}\b', combined):
                metadata["jenjang"] = j
                break
        
        # Extract cabang - common branches
        cabang_keywords = [
            "pulogadung", "kelapa gading", "jakarta", 
            "cibinong", "bogor", "bekasi", "tangerang"
        ]
        for c in cabang_keywords:
            if c in combined:
                metadata["cabang"] = c.title()
                break
        
        # Extract tahun
        tahun_patterns = [
            r'20\d{2}/20\d{2}',
            r'20\d{2}-20\d{2}',
            r'tahun\s+ajaran\s+20\d{2}',
            r'20\d{2}'
        ]
        for pattern in tahun_patterns:
            match = re.search(pattern, knowledge_text)
            if match:
                metadata["tahun"] = match.group().replace("tahun ajaran ", "").strip()
                break
        
        # Detect doc type
        if "FAQ" in knowledge_text[:500] or "Pertanyaan:" in knowledge_text:
            metadata["doc_type"] = "FAQ"
            metadata["kategori"] = "FAQ"
        elif "BIAYA" in knowledge_text[:500] or "Rp" in knowledge_text[:1000]:
            metadata["doc_type"] = "BIAYA"
            metadata["kategori"] = "Biaya"
        elif "Pasal" in knowledge_text or "SK" in knowledge_text[:500]:
            metadata["doc_type"] = "PERATURAN"
            metadata["kategori"] = "Peraturan"
        else:
            metadata["doc_type"] = "GENERAL"
        
        return metadata
