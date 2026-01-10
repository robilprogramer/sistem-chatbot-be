# app/services/pdf_extractor.py
from __future__ import annotations  # ✅ WAJIB
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

@dataclass
class ExtractionResult:
    """Result dari ekstraksi PDF"""
    raw_text: str  # Gabungan semua text dari semua page
    total_pages: int
    is_scanned: bool
    extraction_method: str
    tables_data: List[Dict]
    images_data: List[Dict]
    layout_info: Dict
    ocr_confidence: Optional[float]
    extraction_duration: float

class PDFExtractor:
    """
    Service untuk ekstraksi PDF dengan output raw text gabungan
    """
    
    def __init__(self, images_dir: str = "./extracted/images", tables_dir: str = "./extracted/tables"):
        self.images_dir = Path(images_dir)
        self.tables_dir = Path(tables_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.tables_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize OCR
        self.reader = easyocr.Reader(['id', 'en'], gpu=False)
    
    def detect_if_scanned(self, pdf_path: str, sample_pages: int = 3) -> bool:
        """Deteksi apakah PDF hasil scan"""
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
    
    def extract_text_native(self, page: fitz.Page) -> str:
        """Ekstrak text dari native PDF"""
        blocks = page.get_text("blocks")
        sorted_blocks = sorted(blocks, key=lambda b: (b[1], b[0]))
        
        text_content = []
        for block in sorted_blocks:
            if block[6] == 0:  # Text block
                text_content.append(block[4])
        
        return "\n\n".join(text_content)
    
    def extract_text_ocr(self, page_image: Image.Image) -> Tuple[str, float]:
        """Ekstrak text menggunakan OCR"""
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
    
    def extract_tables(self, pdf_path: str, page_num: int) -> List[Dict]:
        """Ekstrak tables dari page"""
        tables_data = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                page = pdf.pages[page_num]
                tables = page.extract_tables()
                
                for idx, table in enumerate(tables):
                    if table:
                        tables_data.append({
                            'page': page_num + 1,
                            'table_index': idx,
                            'method': 'pdfplumber',
                            'data': table,
                            'markdown': self._table_to_markdown(table)
                        })
        except Exception as e:
            print(f"Table extraction error (page {page_num + 1}): {str(e)}")
        
        return tables_data
    
    def _table_to_markdown(self, table: List[List]) -> str:
        """Convert table to markdown"""
        if not table:
            return ""
        
        md_lines = []
        if table[0]:
            md_lines.append("| " + " | ".join(str(cell or "") for cell in table[0]) + " |")
            md_lines.append("|" + "|".join(["---" for _ in table[0]]) + "|")
        
        for row in table[1:]:
            if row:
                md_lines.append("| " + " | ".join(str(cell or "") for cell in row) + " |")
        
        return "\n".join(md_lines)
    
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
        Main function: Process PDF dan return RAW TEXT GABUNGAN
        """
        start_time = time.time()
        
        print(f"\n🚀 Processing PDF (doc_id: {doc_id}): {Path(pdf_path).name}")
        
        # Detect if scanned
        is_scanned = self.detect_if_scanned(pdf_path)
        print(f"   PDF Type: {'SCANNED' if is_scanned else 'NATIVE'}")
        
        # Open PDF
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        # Containers untuk hasil gabungan
        all_texts = []
        all_tables = []
        all_images = []
        all_confidences = []
        
        # Process setiap page
        for page_num in range(total_pages):
            print(f"   Processing page {page_num + 1}/{total_pages}...", end=" ")
            
            page = doc[page_num]
            
            # Extract text
            if is_scanned:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                text, ocr_conf = self.extract_text_ocr(img)
                all_confidences.append(ocr_conf)
                extraction_method =ExtractionMethod.OCR
            else:
                text = self.extract_text_native(page)
                extraction_method = ExtractionMethod.NATIVE
            
            all_texts.append(text)
            
            # Extract tables
            tables = self.extract_tables(pdf_path, page_num)
            all_tables.extend(tables)
            
            # Extract images
            images = self.extract_images(pdf_path, page_num, doc_id)
            all_images.extend(images)
            
            print("✓")
        
        doc.close()
        
        # GABUNGKAN SEMUA TEXT JADI SATU RAW TEXT
        raw_text = "\n\n---PAGE BREAK---\n\n".join(all_texts)
        
        # Calculate avg OCR confidence
        avg_ocr_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else None
        
        # Layout info (summary)
        layout_info = {
            "total_pages": total_pages,
            "total_tables": len(all_tables),
            "total_images": len(all_images),
            "pages_with_tables": len(set(t['page'] for t in all_tables)),
            "pages_with_images": len(set(i['page'] for i in all_images))
        }
        
        extraction_duration = time.time() - start_time
        
        print(f"\n✅ Extraction completed in {extraction_duration:.2f}s")
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