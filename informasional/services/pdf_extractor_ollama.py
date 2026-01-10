# app/services/pdf_extractor_ollama.py
"""
PDF Extractor with Ollama - Full Document Summarization
Raw text = AI summary yang mudah dibaca
"""
from __future__ import annotations
import os
import io
import time
import requests
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import fitz  # PyMuPDF
from PIL import Image
import pdfplumber
import easyocr
import numpy as np
import base64
from models.document import ExtractionMethod
from tqdm import tqdm

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


class OllamaPDFExtractor:
    """
    PDF Extractor dengan full document summarization
    Raw text = readable AI summary
    """
    
    def __init__(self, 
                 images_dir: str = "./extracted/images", 
                 tables_dir: str = "./extracted/tables",
                 use_ollama: bool = True,
                 ollama_base_url: str = "http://localhost:11434",
                 ollama_model: str = "llama3.2:latest",  # Text model cukup
                 show_progress: bool = True,
                 summarize_mode: bool = True):  # ✅ NEW: Enable summary mode
        
        self.images_dir = Path(images_dir)
        self.tables_dir = Path(tables_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.tables_dir.mkdir(parents=True, exist_ok=True)
        
        self.show_progress = show_progress
        self.summarize_mode = summarize_mode  # ✅ NEW
        
        # Initialize OCR
        try:
            self.reader = easyocr.Reader(['id', 'en'], gpu=False)
            self.ocr_available = True
            print("✅ OCR initialized")
        except Exception as e:
            print(f"⚠️  OCR initialization failed: {e}")
            self.ocr_available = False
        
        # Initialize Ollama
        self.use_ollama = use_ollama
        self.ollama_base_url = ollama_base_url
        self.ollama_model = ollama_model
        
        if use_ollama:
            self.ollama_available = self._check_ollama_connection()
        else:
            self.ollama_available = False
    
    def _check_ollama_connection(self) -> bool:
        """Check apakah Ollama server running"""
        try:
            response = requests.get(f"{self.ollama_base_url}/api/tags", timeout=2)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m['name'] for m in models]
                print(f"✅ Ollama connected. Available models: {model_names}")
                
                if not any(self.ollama_model in name for name in model_names):
                    print(f"⚠️  Model '{self.ollama_model}' not found. Available: {model_names}")
                    print(f"   Run: ollama pull {self.ollama_model}")
                    return False
                
                return True
            return False
        except Exception as e:
            print(f"⚠️  Ollama not available: {e}")
            print(f"   Make sure Ollama is running: ollama serve")
            return False
    
    def _call_ollama(self, prompt: str, image_base64: Optional[str] = None, desc: str = "") -> str:
        """Call Ollama API"""
        if not self.ollama_available:
            return ""
        
        try:
            url = f"{self.ollama_base_url}/api/generate"
            
            payload = {
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "num_ctx": 8192  # Context window lebih besar untuk full doc
                }
            }
            
            if image_base64 and "vision" in self.ollama_model:
                payload["images"] = [image_base64]
            
            if desc and self.show_progress:
                print(f"      🤖 {desc}...", end=" ", flush=True)
            
            response = requests.post(url, json=payload, timeout=900)  # Longer timeout
            
            if response.status_code == 200:
                result = response.json()
                if desc and self.show_progress:
                    print("✅")
                return result.get('response', '').strip()
            else:
                if desc and self.show_progress:
                    print("❌")
                print(f"⚠️  Ollama API error: {response.status_code}")
                return ""
                
        except Exception as e:
            if desc and self.show_progress:
                print("❌")
            print(f"⚠️  Ollama call error: {e}")
            return ""
    
    
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
        ✅ NEW: Summarize entire document dengan Ollama
        Return: Human-readable summary dalam Bahasa Indonesia
        """
        if not self.use_ollama or not self.ollama_available:
            # Fallback: return structured text
            return self._construct_structured_text(all_text, tables, images)
        
        print("\n🤖 Generating document summary with Ollama...")
        
        # Prepare document content
        doc_content = f"=== JUDUL DOKUMEN ===\n{doc_title}\n\n"
        doc_content += f"=== ISI DOKUMEN ===\n{all_text[:4000]}\n\n"  # Limit text
        
        # Add tables
        if tables:
            doc_content += "=== TABEL ===\n"
            for idx, table in enumerate(tables[:3]):  # Max 3 tables
                doc_content += f"\nTabel {idx + 1}:\n"
                doc_content += table.get('markdown', '')[:1000] + "\n"
        
        # Prompt untuk summarization
        prompt = f"""Anda adalah asisten AI yang ahli dalam menganalisis dan meringkas dokumen.

Dokumen berikut perlu Anda ringkas dan jelaskan dalam Bahasa Indonesia yang jelas dan mudah dipahami.

{doc_content}

TUGAS ANDA:
1. Buat ringkasan lengkap dokumen dalam Bahasa Indonesia
2. Jelaskan tujuan dan isi utama dokumen
3. Jika ada tabel, jelaskan isi tabel dengan detail (kategori, nilai, informasi penting)
4. Jelaskan informasi kunci yang perlu diketahui pembaca
5. Susun dalam format yang terstruktur dan mudah dipahami

FORMAT YANG DIHARAPKAN:
- Gunakan paragraf yang jelas
- Jelaskan angka dan data penting
- Highlight poin-poin kunci
- Hindari bullet points, gunakan narasi mengalir

Berikan ringkasan lengkap dalam Bahasa Indonesia:"""

        summary = self._call_ollama(
            prompt=prompt,
            desc="Summarizing full document"
        )
        
        if summary:
            return summary
        else:
            # Fallback
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
            parts.append(text.strip()[:2000])  # Limit
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
        print(f"🚀 PDF EXTRACTION WITH OLLAMA")
        print(f"   Mode: {'📝 SUMMARIZE' if self.summarize_mode else '📄 EXTRACT'}")
        print(f"{'='*70}")
        print(f"📄 File: {Path(pdf_path).name}")
        print(f"🆔 Doc ID: {doc_id}")
        print(f"🤖 Ollama Model: {self.ollama_model}")
        print(f"🔧 Ollama Status: {'✅ Available' if self.ollama_available else '❌ Not Available'}")
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
                
                #Extract images (skip interpretation untuk speed)
                images = self.extract_images(pdf_path, page_num, doc_id)
                all_images.extend(images)
            
            doc.close()
            
            # ✅ GENERATE AI SUMMARY sebagai raw_text
            print("\n📦 Generating document summary...")
            
            combined_text = "\n\n".join(all_texts)
            doc_title = Path(pdf_path).stem
            
            if self.summarize_mode and self.use_ollama and self.ollama_available:
                raw_text = self._summarize_full_document(
                    all_text=combined_text,
                    tables=all_tables,
                    images=all_images,
                    doc_title=doc_title
                )
            else:
                # Fallback: structured text
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
                "ollama_enhanced": self.use_ollama and self.ollama_available,
                "ollama_model": self.ollama_model if self.ollama_available else None,
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