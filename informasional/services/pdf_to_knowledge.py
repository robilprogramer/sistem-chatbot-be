
from __future__ import annotations
import os
import time
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
import fitz 
import pdfplumber 
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

@dataclass
class KnowledgeResult:
    """Result dari konversi PDF ke knowledge base"""
    knowledge_text: str  # Text final yang sudah ditulis ulang AI
    total_pages: int
    original_length: int
    knowledge_length: int
    has_tables: bool
    processing_duration: float
    ai_model: str

class PDFToKnowledgeConverter:
    """
    Converter sederhana: PDF → AI-generated Knowledge Base
    """
    
    def __init__(self,openai_api_key: Optional[str] = None,model: str = "gpt-4o-mini"):
        
        # Initialize OpenAI
        if not openai_api_key:
            openai_api_key = os.getenv("OPENAI_API_KEY")
        
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY required")
        
        self.llm = ChatOpenAI(
            model=model,
            temperature=0.3,
            api_key=openai_api_key,
            max_tokens=4000
        )
        
        self.model = model
        print(f"✅ PDF to Knowledge Converter initialized")
        print(f"   AI Model: {model}")
    
    def extract_pdf_content(self, pdf_path: str) -> tuple[str, List[Dict], int]:
        """
        Step 1: Extract raw content dari PDF (simple)
        Returns: (text, tables, total_pages)
        """
        print(f"\n📄 Extracting content from: {Path(pdf_path).name}")
        
        # Extract text dengan PyMuPDF
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        all_text = []
        for page_num in range(total_pages):
            page = doc[page_num]
            text = page.get_text()
            if text.strip():
                all_text.append(text)
        
        doc.close()
        
        combined_text = "\n\n".join(all_text)
        
        # Extract tables dengan pdfplumber
        tables = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    page_tables = page.extract_tables()
                    if page_tables:
                        for idx, table in enumerate(page_tables):
                            if table:
                                tables.append({
                                    'page': page_num + 1,
                                    'data': table,
                                    'markdown': self._table_to_markdown(table)
                                })
        except Exception as e:
            print(f"⚠️  Table extraction error: {e}")
        
        print(f"   ✓ Extracted {len(combined_text)} characters")
        print(f"   ✓ Found {len(tables)} tables")
        print(f"   ✓ Total pages: {total_pages}")
        
        return combined_text, tables, total_pages
    
    def _table_to_markdown(self, table: List[List]) -> str:
        """Convert table to markdown"""
        if not table:
            return ""
        
        md_lines = []
        
        # Header
        if table[0]:
            header = [str(cell or "").strip() for cell in table[0]]
            md_lines.append("| " + " | ".join(header) + " |")
            md_lines.append("|" + "|".join(["---" for _ in header]) + "|")
        
        # Rows
        for row in table[1:]:
            if row:
                row_data = [str(cell or "").strip() for cell in row]
                md_lines.append("| " + " | ".join(row_data) + " |")
        
        return "\n".join(md_lines)
    
    def ai_rewrite_to_knowledge(self, 
                                 text: str, 
                                 tables: List[Dict],
                                 doc_title: str) -> str:
        """
        Step 2: AI menulis ulang menjadi knowledge base yang terstruktur
        """
        print(f"\n🤖 AI is rewriting document into knowledge base...")
        
        # Prepare content untuk AI
        content = f"JUDUL DOKUMEN: {doc_title}\n\n"
        
        # Limit text kalau terlalu panjang
        if len(text) > 8000:
            content += f"ISI DOKUMEN (excerpt):\n{text[:8000]}...\n\n"
        else:
            content += f"ISI DOKUMEN:\n{text}\n\n"
        
        # Add tables
        if tables:
            content += "TABEL:\n"
            for idx, table in enumerate(tables[:3]):  # Max 3 tables
                content += f"\nTabel {idx + 1} (Halaman {table['page']}):\n"
                content += table.get('markdown', '')[:1000] + "\n"
        
        # System prompt
        system_prompt = """Anda adalah asisten AI yang ahli dalam mengubah dokumen PDF menjadi knowledge base yang terstruktur dan mudah dipahami.

Tugas Anda: Tulis ulang dokumen ini menjadi knowledge base yang lengkap dan informatif dalam Bahasa Indonesia.

PENTING:
- Jangan membuat ringkasan, tapi tulis ulang SEMUA informasi penting dengan lengkap
- Jelaskan SEMUA data, angka, kategori, dan detail dengan jelas
- Jika ada tabel, jelaskan SEMUA baris dan kolom dengan detail
- Gunakan bahasa yang natural dan mudah dipahami
- Susun dalam paragraf yang mengalir (TIDAK pakai bullet points)
- Fokus pada akurasi dan kelengkapan informasi"""

        # User prompt
        user_prompt = f"""{content}

Tulis ulang dokumen di atas menjadi knowledge base yang lengkap dan terstruktur dalam Bahasa Indonesia.

PEDOMAN:
1. Mulai dengan penjelasan tujuan/konteks dokumen
2. Jelaskan SEMUA informasi penting secara detail
3. Jika ada tabel, jelaskan SEMUA kategori dan nilai dengan lengkap
4. Gunakan paragraf yang mengalir (hindari bullet points)
5. Pastikan TIDAK ada informasi yang hilang
6. Tulis dengan bahasa yang jelas dan mudah dipahami

Hasil knowledge base:"""

        try:
            # Call OpenAI
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = self.llm.invoke(messages)
            knowledge_text = response.content.strip()
            
            print(f"   ✓ AI rewriting completed")
            print(f"   ✓ Knowledge base length: {len(knowledge_text)} characters")
            
            return knowledge_text
            
        except Exception as e:
            print(f"   ✗ AI rewriting failed: {e}")
            # Fallback: return original with structure
            return self._fallback_structure(text, tables)
    
    def _fallback_structure(self, text: str, tables: List[Dict]) -> str:
        """Fallback jika AI gagal"""
        parts = [
            "=== KNOWLEDGE BASE ===\n",
            text[:3000],
        ]
        
        if tables:
            parts.append("\n\n=== INFORMASI TABEL ===\n")
            for idx, table in enumerate(tables):
                parts.append(f"\nTabel {idx + 1}:\n{table.get('markdown', '')}\n")
        
        return "\n".join(parts)
    
    def process(self, pdf_path: str, doc_title: Optional[str] = None) -> KnowledgeResult:
        """
        Main function: PDF → Knowledge Base
        """
        start_time = time.time()
        
        if not doc_title:
            doc_title = Path(pdf_path).stem
        
        print(f"\n{'='*70}")
        print(f"🚀 PDF TO KNOWLEDGE BASE CONVERTER")
        print(f"{'='*70}")
        print(f"📄 File: {Path(pdf_path).name}")
        print(f"🤖 AI Model: {self.model}")
        print(f"{'='*70}")
        
        # Step 1: Extract content
        text, tables, total_pages = self.extract_pdf_content(pdf_path)
        
        # Step 2: AI rewrite
        knowledge_text = self.ai_rewrite_to_knowledge(text, tables, doc_title)
        
        duration = time.time() - start_time
        
        print(f"\n{'='*70}")
        print(f"✅ CONVERSION COMPLETED")
        print(f"{'='*70}")
        print(f"⏱️  Duration: {duration:.2f}s")
        print(f"📄 Pages: {total_pages}")
        print(f"📝 Original: {len(text):,} chars")
        print(f"✨ Knowledge Base: {len(knowledge_text):,} chars")
        print(f"📊 Tables: {len(tables)}")
        print(f"{'='*70}\n")
        
        return KnowledgeResult(
            knowledge_text=knowledge_text,
            total_pages=total_pages,
            original_length=len(text),
            knowledge_length=len(knowledge_text),
            has_tables=len(tables) > 0,
            processing_duration=duration,
            ai_model=self.model
        )