# app/services/pdf_extractor_enhanced.py
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
from models.document import ExtractionMethod
import anthropic  # atau openai
import base64

@dataclass
class ExtractionResult:
    """Result dari ekstraksi PDF"""
    raw_text: str  
    total_pages: int
    is_scanned: bool
    extraction_method: str
    tables_data: List[Dict]
    images_data: List[Dict]
    layout_info: Dict
    ocr_confidence: Optional[float]
    extraction_duration: float

class EnhancedPDFExtractor:
    """
    Enhanced PDF Extractor dengan LLM untuk interpretasi tabel dan images
    """
    
    def __init__(self, 
                 images_dir: str = "./extracted/images", 
                 tables_dir: str = "./extracted/tables",
                 use_llm: bool = True,
                 anthropic_api_key: Optional[str] = None):
        self.images_dir = Path(images_dir)
        self.tables_dir = Path(tables_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.tables_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize OCR
        try:
            self.reader = easyocr.Reader(['id', 'en'], gpu=False)
            self.ocr_available = True
        except Exception as e:
            print(f"⚠️  OCR initialization failed: {e}")
            self.ocr_available = False
        
        # Initialize LLM
        self.use_llm = use_llm
        if use_llm and anthropic_api_key:
            self.llm_client = anthropic.Anthropic(api_key=anthropic_api_key)
        else:
            self.llm_client = None
            print("⚠️  LLM not initialized. Set anthropic_api_key for better table interpretation.")
    
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
                if block[6] == 0:  # Text block
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
            img_array = np.array(page_image)
            results = self.reader.readtext(img_array, detail=1)
            
            if not results:
                return "", 0.0
            
            texts = []
            confidences = []
            
            for (bbox, text, conf) in results:
                texts.append(text)
                confidences.append(conf)
            
            full_text = "\n".join(texts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            return full_text, avg_confidence
        except Exception as e:
            print(f"⚠️  OCR error: {e}")
            return "", 0.0
    
    def extract_tables_enhanced(self, pdf_path: str, page_num: int) -> List[Dict]:
        """
        Enhanced table extraction dengan multiple methods
        """
        tables_data = []
        
        # Method 1: pdfplumber
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if page_num < len(pdf.pages):
                    page = pdf.pages[page_num]
                    tables = page.extract_tables()
                    
                    for idx, table in enumerate(tables):
                        if table and len(table) > 0:
                            # Clean table data
                            cleaned_table = self._clean_table(table)
                            
                            tables_data.append({
                                'page': page_num + 1,
                                'table_index': idx,
                                'method': 'pdfplumber',
                                'data': cleaned_table,
                                'markdown': self._table_to_markdown(cleaned_table),
                                'row_count': len(cleaned_table),
                                'col_count': len(cleaned_table[0]) if cleaned_table else 0
                            })
        except Exception as e:
            print(f"⚠️  pdfplumber table extraction error (page {page_num + 1}): {str(e)}")
        
        # Method 2: Extract table as image and use vision LLM
        if self.use_llm and self.llm_client and len(tables_data) > 0:
            try:
                # Get page as image
                doc = fitz.open(pdf_path)
                page = doc[page_num]
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                doc.close()
                
                # Convert to base64 for Claude
                buffered = io.BytesIO()
                img.save(buffered, format="PNG")
                img_base64 = base64.b64encode(buffered.getvalue()).decode()
                
                # Use Claude to interpret table
                table_interpretation = self._interpret_table_with_llm(img_base64, tables_data)
                
                # Add interpretation to first table
                if table_interpretation and len(tables_data) > 0:
                    tables_data[0]['llm_interpretation'] = table_interpretation
                
            except Exception as e:
                print(f"⚠️  LLM table interpretation error: {e}")
        
        return tables_data
    
    def _clean_table(self, table: List[List]) -> List[List]:
        """Clean empty cells and normalize table"""
        if not table:
            return []
        
        cleaned = []
        for row in table:
            if row and any(cell for cell in row if cell):  # Skip empty rows
                cleaned_row = [str(cell).strip() if cell else "" for cell in row]
                cleaned.append(cleaned_row)
        
        return cleaned
    
    def _table_to_markdown(self, table: List[List]) -> str:
        """Convert table to markdown dengan handling yang lebih baik"""
        if not table or len(table) == 0:
            return ""
        
        try:
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
        except Exception as e:
            print(f"⚠️  Markdown conversion error: {e}")
            return str(table)
    
    def _interpret_table_with_llm(self, image_base64: str, tables_data: List[Dict]) -> str:
        """
        Gunakan Claude Vision untuk interpretasi tabel yang lebih baik
        """
        if not self.llm_client:
            return ""
        
        try:
            # Ambil markdown table pertama
            markdown_table = tables_data[0].get('markdown', '') if tables_data else ''
            
            message = self.llm_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_base64,
                                },
                            },
                            {
                                "type": "text",
                                "text": f"""Analisis tabel dalam gambar ini dan berikan interpretasi dalam bahasa Indonesia yang jelas dan terstruktur.

Tabel mentah yang sudah di-extract:
{markdown_table}

Tugas Anda:
1. Jelaskan isi tabel dengan lengkap dalam bentuk narasi
2. Sebutkan semua kategori dan nilai penting
3. Highlight informasi kunci yang perlu diperhatikan
4. Format dalam paragraf yang mudah dipahami

Berikan interpretasi lengkap dalam bahasa Indonesia:"""
                            }
                        ],
                    }
                ],
            )
            
            interpretation = message.content[0].text
            return interpretation
            
        except Exception as e:
            print(f"⚠️  LLM interpretation error: {e}")
            return ""
    
    def _interpret_image_with_llm(self, image_path: str) -> str:
        """
        Interpretasi gambar/logo dengan Claude Vision
        """
        if not self.llm_client:
            return ""
        
        try:
            # Read and encode image
            with open(image_path, "rb") as img_file:
                img_data = img_file.read()
                img_base64 = base64.b64encode(img_data).decode()
            
            message = self.llm_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": img_base64,
                                },
                            },
                            {
                                "type": "text",
                                "text": "Deskripsikan gambar ini dalam bahasa Indonesia. Jika ini logo atau diagram, jelaskan apa yang ada dalam gambar tersebut."
                            }
                        ],
                    }
                ],
            )
            
            return message.content[0].text
            
        except Exception as e:
            print(f"⚠️  Image interpretation error: {e}")
            return ""
    
    def extract_images(self, pdf_path: str, page_num: int, doc_id: int) -> List[Dict]:
        """Ekstrak images dari page dengan LLM interpretation"""
        images_data = []
        
        try:
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
                    
                    # LLM interpretation
                    description = ""
                    if self.use_llm and self.llm_client:
                        # Skip very small images (likely icons)
                        if image.width > 100 and image.height > 100:
                            description = self._interpret_image_with_llm(str(image_path))
                    
                    images_data.append({
                        'page': page_num + 1,
                        'filename': image_filename,
                        'path': str(image_path),
                        'width': image.width,
                        'height': image.height,
                        'format': image_ext,
                        'size_bytes': len(image_bytes),
                        'description': description
                    })
                except Exception as e:
                    print(f"⚠️  Image extraction error (page {page_num + 1}, img {img_index}): {str(e)}")
            
            doc.close()
        except Exception as e:
            print(f"⚠️  Error opening PDF for images: {e}")
        
        return images_data
    
    def construct_enhanced_text(self, 
                                text: str, 
                                tables: List[Dict], 
                                images: List[Dict]) -> str:
        """
        Gabungkan text, table interpretation, dan image description
        """
        parts = []
        
        # 1. Original text
        if text.strip():
            parts.append(text.strip())
        
        # 2. Table interpretations
        if tables:
            parts.append("\n\n=== INFORMASI TABEL ===\n")
            for idx, table in enumerate(tables):
                parts.append(f"\n--- Tabel {idx + 1} (Halaman {table['page']}) ---")
                
                # Jika ada LLM interpretation, pakai itu
                if 'llm_interpretation' in table and table['llm_interpretation']:
                    parts.append(f"\n{table['llm_interpretation']}")
                else:
                    # Fallback ke markdown
                    parts.append(f"\n{table.get('markdown', '')}")
        
        # 3. Image descriptions
        if images:
            image_descriptions = [img for img in images if img.get('description')]
            if image_descriptions:
                parts.append("\n\n=== DESKRIPSI GAMBAR ===\n")
                for idx, img in enumerate(image_descriptions):
                    parts.append(f"\n--- Gambar {idx + 1} (Halaman {img['page']}) ---")
                    parts.append(f"{img['description']}")
        
        return "\n".join(parts)
    
    def process_pdf(self, pdf_path: str, doc_id: int) -> ExtractionResult:
        """
        Main function: Process PDF dengan enhanced extraction
        """
        start_time = time.time()
        
        print(f"\n🚀 Processing PDF (Enhanced Mode, doc_id: {doc_id}): {Path(pdf_path).name}")
        
        # Detect if scanned
        is_scanned = self.detect_if_scanned(pdf_path)
        print(f"   PDF Type: {'SCANNED' if is_scanned else 'NATIVE'}")
        
        try:
            # Open PDF
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            
            # Containers
            all_texts = []
            all_tables = []
            all_images = []
            all_confidences = []
            
            # Process setiap page
            for page_num in range(total_pages):
                print(f"   Processing page {page_num + 1}/{total_pages}...", end=" ")
                
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
                    extraction_method = ExtractionMethod.NATIVE
                
                # Extract tables (enhanced)
                tables = self.extract_tables_enhanced(pdf_path, page_num)
                all_tables.extend(tables)
                
                # Extract images (with LLM)
                images = self.extract_images(pdf_path, page_num, doc_id)
                all_images.extend(images)
                
                # Construct enhanced text for this page
                page_enhanced_text = self.construct_enhanced_text(text, tables, images)
                all_texts.append(page_enhanced_text)
                
                print("✓")
            
            doc.close()
            
            # GABUNGKAN SEMUA ENHANCED TEXT
            raw_text = "\n\n---PAGE BREAK---\n\n".join(all_texts)
            
            # Calculate metrics
            avg_ocr_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else None
            
            layout_info = {
                "total_pages": total_pages,
                "total_tables": len(all_tables),
                "total_images": len(all_images),
                "pages_with_tables": len(set(t['page'] for t in all_tables)),
                "pages_with_images": len(set(i['page'] for i in all_images)),
                "llm_enhanced": self.use_llm and self.llm_client is not None
            }
            
            extraction_duration = time.time() - start_time
            
            print(f"\n✅ Enhanced extraction completed in {extraction_duration:.2f}s")
            print(f"   Total text length: {len(raw_text)} chars")
            print(f"   Tables: {len(all_tables)}, Images: {len(all_images)}")
            
            return ExtractionResult(
                raw_text=raw_text,
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
            print(f"\n❌ Enhanced PDF processing failed: {e}")
            raise e