# app/services/pdf_extractor_langchain.py
"""
PDF Extractor with LangChain + OpenAI - Full Document Summarization
Raw text = AI summary yang mudah dibaca
"""
from __future__ import annotations
import os
import io
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import fitz  # PyMuPDF
from PIL import Image
import pdfplumber
import easyocr
import numpy as np
import base64
from tqdm import tqdm

# LangChain imports
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from models.document import ExtractionMethod

@dataclass
class ExtractionResult:
    """Result dari ekstraksi PDF"""
    raw_text: str  # ✅ SEKARANG INI AI SUMMARY, BUKAN RAW TEXT
    total_pages: int
    is_scanned: bool
    extraction_method: str
    tables_data: List[Dict]
    images_data: List[Dict]
    layout_info: Dict
    ocr_confidence: Optional[float]
    extraction_duration: float


class LangChainPDFExtractor:
    """
    PDF Extractor dengan LangChain + OpenAI
    Full document summarization mode
    """
    
    def __init__(self, 
                 images_dir: str = "./extracted/images", 
                 tables_dir: str = "./extracted/tables",
                 use_openai: bool = True,
                 openai_api_key: Optional[str] = None,
                 model_name: str = "gpt-4o-mini",
                 temperature: float = 0.3,
                 show_progress: bool = True,
                 summarize_mode: bool = True):  # ✅ NEW
        
        self.images_dir = Path(images_dir)
        self.tables_dir = Path(tables_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.tables_dir.mkdir(parents=True, exist_ok=True)
        
        self.show_progress = show_progress
        self.use_openai = use_openai
        self.model_name = model_name
        self.summarize_mode = summarize_mode  # ✅ NEW
        
        # Initialize OCR
        try:
            self.reader = easyocr.Reader(['id', 'en'], gpu=False)
            self.ocr_available = True
            print("✅ OCR initialized")
        except Exception as e:
            print(f"⚠️  OCR initialization failed: {e}")
            self.ocr_available = False
        
        # Initialize LangChain + OpenAI
        if use_openai:
            try:
                if not openai_api_key:
                    openai_api_key = os.getenv("OPENAI_API_KEY")
                
                if not openai_api_key:
                    raise ValueError("OPENAI_API_KEY not found")
                
                # Initialize ChatOpenAI
                self.llm = ChatOpenAI(
                    model=model_name,
                    temperature=temperature,
                    api_key=openai_api_key,
                    max_tokens=4000  # Larger for summaries
                )
                
                # Test connection
                test_response = self.llm.invoke([HumanMessage(content="Test")])
                
                print(f"✅ LangChain + OpenAI initialized")
                print(f"   Model: {model_name}")
                self.openai_available = True
                
            except Exception as e:
                print(f"⚠️  OpenAI initialization failed: {e}")
                self.openai_available = False
                self.llm = None
        else:
            self.openai_available = False
            self.llm = None
    
    def detect_if_scanned(self, pdf_path: str, sample_pages: int = 3) -> bool:
        """Deteksi apakah PDF hasil scan"""
        try:
            doc = fitz.open(pdf_path)
            total_pages = min(len(doc), sample_pages)
            text_chars = 0
            
            for page_num in range(total_pages):
                page = doc[page_num]
                text = page.get_text()
                text_chars += len(text.strip())
            
            doc.close()
            avg_chars = text_chars / total_pages
            return avg_chars < 100
        except Exception as e:
            print(f"⚠️  Error detecting scan: {e}")
            return False
    
    def extract_text_native(self, page) -> str:
        """Ekstrak text dari native PDF"""
        try:
            blocks = page.get_text("blocks")
            sorted_blocks = sorted(blocks, key=lambda b: (b[1], b[0]))
            
            text_content = []
            for block in sorted_blocks:
                if block[6] == 0:
                    text_content.append(block[4])
            
            return "\n\n".join(text_content)
        except Exception as e:
            print(f"⚠️  Error extracting native text: {e}")
            return ""
    
    def extract_text_ocr(self, page_image: Image.Image) -> Tuple[str, float]:
        """Ekstrak text menggunakan OCR"""
        if not self.ocr_available:
            return "", 0.0
        
        try:
            if self.show_progress:
                print(f"      📷 OCR processing...", end=" ", flush=True)
            
            img_array = np.array(page_image)
            results = self.reader.readtext(img_array, detail=1)
            
            if not results:
                if self.show_progress:
                    print("⚠️ No text found")
                return "", 0.0
            
            texts = []
            confidences = []
            
            for (bbox, text, conf) in results:
                texts.append(text)
                confidences.append(conf)
            
            full_text = "\n".join(texts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            if self.show_progress:
                print(f"✅ (conf: {avg_confidence:.1%})")
            
            return full_text, avg_confidence
        except Exception as e:
            if self.show_progress:
                print("❌")
            print(f"⚠️  OCR error: {e}")
            return "", 0.0
    
    def extract_tables_enhanced(self, pdf_path: str, page_num: int) -> List[Dict]:
        """Enhanced table extraction"""
        tables_data = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if page_num < len(pdf.pages):
                    page = pdf.pages[page_num]
                    tables = page.extract_tables()
                    
                    if tables and self.show_progress:
                        print(f"      📊 Found {len(tables)} table(s)")
                    
                    for idx, table in enumerate(tables):
                        if table and len(table) > 0:
                            cleaned_table = self._clean_table(table)
                            
                            if cleaned_table:
                                markdown = self._table_to_markdown(cleaned_table)
                                
                                tables_data.append({
                                    'page': page_num + 1,
                                    'table_index': idx,
                                    'method': 'pdfplumber',
                                    'data': cleaned_table,
                                    'markdown': markdown,
                                    'row_count': len(cleaned_table),
                                    'col_count': len(cleaned_table[0]) if cleaned_table else 0
                                })
        except Exception as e:
            print(f"      ⚠️  Table extraction error: {str(e)}")
        
        return tables_data
    
    def _clean_table(self, table: List[List]) -> List[List]:
        """Clean table"""
        if not table:
            return []
        
        cleaned = []
        for row in table:
            if row and any(cell for cell in row if cell):
                cleaned_row = [str(cell).strip() if cell else "" for cell in row]
                cleaned.append(cleaned_row)
        
        return cleaned
    
    def _table_to_markdown(self, table: List[List]) -> str:
        """Convert to markdown"""
        if not table or len(table) == 0:
            return ""
        
        try:
            md_lines = []
            
            if table[0]:
                header = [str(cell or "").strip() for cell in table[0]]
                md_lines.append("| " + " | ".join(header) + " |")
                md_lines.append("|" + "|".join(["---" for _ in header]) + "|")
            
            for row in table[1:]:
                if row:
                    row_data = [str(cell or "").strip() for cell in row]
                    md_lines.append("| " + " | ".join(row_data) + " |")
            
            return "\n".join(md_lines)
        except Exception as e:
            print(f"⚠️  Markdown conversion error: {e}")
            return str(table)
    
    def _summarize_full_document(self, 
                                 all_text: str, 
                                 tables: List[Dict], 
                                 images: List[Dict],
                                 doc_title: str = "") -> str:
        """
        ✅ NEW: Summarize entire document dengan LangChain + OpenAI
        Return: Human-readable summary dalam Bahasa Indonesia
        """
        if not self.use_openai or not self.openai_available or not self.llm:
            return self._construct_structured_text(all_text, tables, images)
        
        print("\n🤖 Generating document summary with OpenAI...")
        
        try:
            # Prepare document content
            doc_content = f"=== JUDUL DOKUMEN ===\n{doc_title}\n\n"
            doc_content += f"=== ISI DOKUMEN ===\n{all_text[:6000]}\n\n"  # GPT has larger context
            
            # Add tables
            if tables:
                doc_content += "=== TABEL ===\n"
                for idx, table in enumerate(tables[:5]):  # Max 5 tables
                    doc_content += f"\nTabel {idx + 1}:\n"
                    doc_content += table.get('markdown', '')[:1500] + "\n"
            
            # System message
            system_message = """Anda adalah asisten AI yang ahli dalam menganalisis dan meringkas dokumen dalam Bahasa Indonesia.
Tugas Anda adalah membuat ringkasan yang lengkap, jelas, dan mudah dipahami."""

            # Human message
            human_message = f"""Dokumen berikut perlu Anda ringkas dan jelaskan dalam Bahasa Indonesia yang jelas dan mudah dipahami.

{doc_content}

TUGAS ANDA:
1. Buat ringkasan lengkap dokumen dalam Bahasa Indonesia
2. Jelaskan tujuan dan isi utama dokumen
3. Jika ada tabel, jelaskan isi tabel dengan detail (semua kategori, nilai, dan informasi penting)
4. Jelaskan informasi kunci yang perlu diketahui pembaca
5. Susun dalam format yang terstruktur dan mudah dipahami

FORMAT YANG DIHARAPKAN:
- Gunakan paragraf yang jelas dan mengalir
- Jelaskan semua angka dan data penting dengan detail
- Highlight poin-poin kunci
- Hindari bullet points, gunakan narasi yang natural
- Berikan konteks yang membantu pemahaman

Berikan ringkasan lengkap dalam Bahasa Indonesia:"""

            # Call OpenAI via LangChain
            messages = [
                SystemMessage(content=system_message),
                HumanMessage(content=human_message)
            ]
            
            if self.show_progress:
                print("      🤖 Calling OpenAI API...", end=" ", flush=True)
            
            response = self.llm.invoke(messages)
            summary = response.content.strip()
            
            if self.show_progress:
                print("✅")
            
            if summary:
                return summary
            else:
                return self._construct_structured_text(all_text, tables, images)
                
        except Exception as e:
            print(f"\n⚠️  OpenAI summarization error: {e}")
            return self._construct_structured_text(all_text, tables, images)
    
    def _construct_structured_text(self, 
                                   text: str, 
                                   tables: List[Dict], 
                                   images: List[Dict]) -> str:
        """
        Fallback: Construct structured readable text
        """
        parts = []
        
        parts.append("=== RINGKASAN DOKUMEN ===\n")
        
        # Text
        if text.strip():
            parts.append(text.strip()[:3000])
            parts.append("\n")
        
        # Tables
        if tables:
            parts.append("\n=== INFORMASI TABEL ===\n")
            for idx, table in enumerate(tables):
                parts.append(f"\nTabel {idx + 1} (Halaman {table['page']}):")
                parts.append(table.get('markdown', ''))
                parts.append("\n")
        
        return "\n".join(parts)
    def extract_images(self, pdf_path: str, page_num: int, doc_id: int) -> List[Dict]:
        """Ekstrak images dari page"""
        images_data = []
        doc = fitz.open(pdf_path)
        page = doc[page_num]
        
        image_list = page.get_images()
        
        for img_index, img in enumerate(image_list):
            try:
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Save image
                image_filename = f"doc_{doc_id}_page_{page_num + 1}_img_{img_index + 1}.{image_ext}"
                image_path = self.images_dir / image_filename
                
                with open(image_path, "wb") as img_file:
                    img_file.write(image_bytes)
                
                # Get image info
                image = Image.open(io.BytesIO(image_bytes))
                
                images_data.append({
                    'page': page_num + 1,
                    'filename': image_filename,
                    'path': str(image_path),
                    'width': image.width,
                    'height': image.height,
                    'format': image_ext,
                    'size_bytes': len(image_bytes)
                })
            except Exception as e:
                print(f"Image extraction error (page {page_num + 1}, img {img_index}): {str(e)}")
        
        doc.close()
        return images_data
    def process_pdf(self, pdf_path: str, doc_id: int) -> ExtractionResult:
        """
        Main function: Extract PDF dan generate AI summary
        """
        start_time = time.time()
        
        print(f"\n{'='*70}")
        print(f"🚀 PDF EXTRACTION WITH LANGCHAIN + OPENAI")
        print(f"   Mode: {'📝 SUMMARIZE' if self.summarize_mode else '📄 EXTRACT'}")
        print(f"{'='*70}")
        print(f"📄 File: {Path(pdf_path).name}")
        print(f"🆔 Doc ID: {doc_id}")
        print(f"🤖 Model: {self.model_name}")
        print(f"🔧 OpenAI Status: {'✅ Available' if self.openai_available else '❌ Not Available'}")
        print(f"{'='*70}\n")
        
        # Detect if scanned
        is_scanned = self.detect_if_scanned(pdf_path)
        print(f"📊 PDF Type: {'📸 SCANNED' if is_scanned else '📝 NATIVE'}")
        
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            print(f"📑 Total Pages: {total_pages}\n")
            
            # Containers
            all_texts = []
            all_tables = []
            all_images = []
            all_confidences = []
            
            # Progress bar
            print("🔄 Processing pages:")
            if self.show_progress:
                page_iterator = tqdm(
                    range(total_pages), 
                    desc="   Pages", 
                    unit="page",
                    bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]'
                )
            else:
                page_iterator = range(total_pages)
            
            for page_num in page_iterator:
                if not self.show_progress:
                    print(f"\n   📄 Page {page_num + 1}/{total_pages}")
                
                page = doc[page_num]
                
                # Extract text
                if is_scanned and self.ocr_available:
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    text, ocr_conf = self.extract_text_ocr(img)
                    all_confidences.append(ocr_conf)
                    extraction_method = ExtractionMethod.OCR
                else:
                    text = self.extract_text_native(page)
                    if not self.show_progress:
                        print(f"      📝 Text extracted")
                    extraction_method = ExtractionMethod.NATIVE
                
                all_texts.append(text)
                
                # Extract tables
                tables = self.extract_tables_enhanced(pdf_path, page_num)
                all_tables.extend(tables)
                
                #Skip images for speed (bisa di-enable jika perlu)
                images = self.extract_images(pdf_path, page_num, doc_id)
                all_images.extend(images)
            
            doc.close()
            
            # ✅ GENERATE AI SUMMARY sebagai raw_text
            print("\n📦 Generating document summary with OpenAI...")
            
            combined_text = "\n\n".join(all_texts)
            doc_title = Path(pdf_path).stem
            
            if self.summarize_mode and self.use_openai and self.openai_available:
                raw_text = self._summarize_full_document(
                    all_text=combined_text,
                    tables=all_tables,
                    images=all_images,
                    doc_title=doc_title
                )
            else:
                # Fallback
                raw_text = self._construct_structured_text(
                    combined_text, 
                    all_tables, 
                    all_images
                )
            
            # Metrics
            avg_ocr_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else None
            
            layout_info = {
                "total_pages": total_pages,
                "total_tables": len(all_tables),
                "total_images": len(all_images),
                "pages_with_tables": len(set(t['page'] for t in all_tables)),
                "pages_with_images": len(set(i['page'] for i in all_images)),
                "ai_enhanced": self.use_openai and self.openai_available,
                "ai_model": self.model_name if self.openai_available else None,
                "summarized": self.summarize_mode
            }
            
            extraction_duration = time.time() - start_time
            
            print(f"\n{'='*70}")
            print(f"✅ EXTRACTION COMPLETED")
            print(f"{'='*70}")
            print(f"⏱️  Duration: {extraction_duration:.2f}s")
            print(f"📝 Summary Length: {len(raw_text):,} characters")
            print(f"📊 Tables: {len(all_tables)}")
            print(f"🖼️  Images: {len(all_images)}")
            if avg_ocr_confidence:
                print(f"🎯 OCR Confidence: {avg_ocr_confidence:.1%}")
            print(f"{'='*70}\n")
            
            return ExtractionResult(
                raw_text=raw_text,  # ✅ NOW THIS IS AI SUMMARY
                total_pages=total_pages,
                is_scanned=is_scanned,
                extraction_method=extraction_method,
                tables_data=all_tables,
                images_data=all_images,
                layout_info=layout_info,
                ocr_confidence=avg_ocr_confidence,
                extraction_duration=extraction_duration
            )
        
        except Exception as e:
            print(f"\n❌ PDF processing failed: {e}")
            raise e