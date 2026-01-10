# ============================================================================
# FILE: utils/pdf_parser.py - FULL VERSION (sesuai file asli)
# ============================================================================
"""
PDF Parser dengan multiple OCR methods
Mendukung ekstraksi gambar, tabel, dan teks dari PDF
"""

import os
import time
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from enum import Enum

# Lazy imports - hanya load saat dibutuhkan
PYMUPDF_AVAILABLE = False
UNSTRUCTURED_AVAILABLE = False
TESSERACT_AVAILABLE = False

# Check PyMuPDF (default - fast)
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    pass

# Check others lazily
def check_unstructured():
    global UNSTRUCTURED_AVAILABLE
    try:
        from unstructured.partition.pdf import partition_pdf
        UNSTRUCTURED_AVAILABLE = True
        return True
    except ImportError:
        return False

def check_tesseract():
    global TESSERACT_AVAILABLE
    try:
        import pytesseract
        from pdf2image import convert_from_path
        TESSERACT_AVAILABLE = True
        return True
    except ImportError:
        return False


class OCRMethod(Enum):
    """Metode OCR yang tersedia"""
    PYMUPDF = "pymupdf"           # Fast, lightweight (DEFAULT)
    UNSTRUCTURED = "unstructured" # Advanced, heavy - dengan ekstraksi gambar
    TESSERACT = "tesseract"       # Traditional OCR


class PDFParser:
    """
    PDF Parser dengan support multiple OCR methods
    
    Default: PyMuPDF (fast, lightweight)
    Advanced: Unstructured (dengan ekstraksi gambar dan tabel)
    """
    
    def __init__(
        self, 
        output_dir: str = "data/extracted_data",
        ocr_method: OCRMethod = None,  # Auto-detect best available
        config: dict = None
    ):
        self.output_dir = output_dir
        self.config = config or {}
        
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # Auto-detect best method if not specified
        if ocr_method is None:
            if PYMUPDF_AVAILABLE:
                self.ocr_method = OCRMethod.PYMUPDF
                print("   📄 Using PyMuPDF (fast mode)")
            else:
                self.ocr_method = OCRMethod.UNSTRUCTURED
                print("   📄 Using Unstructured (install pymupdf for faster loading)")
        else:
            self.ocr_method = ocr_method
    
    def parse_with_pymupdf(self, pdf_path: str) -> Tuple[List[str], float]:
        """
        Parse PDF menggunakan PyMuPDF (FAST!)
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Tuple of (texts, processing_time)
        """
        if not PYMUPDF_AVAILABLE:
            raise ImportError("PyMuPDF not installed. Run: pip install pymupdf")
        
        print(f"📄 [PyMuPDF] Parsing: {pdf_path}")
        start_time = time.time()
        
        import fitz
        
        doc = fitz.open(pdf_path)
        texts = []
        
        for i, page in enumerate(doc, 1):
            print(f"   Processing page {i}/{len(doc)}...", end="\r")
            text = page.get_text()
            if text.strip():
                texts.append(text)
        
        doc.close()
        
        processing_time = time.time() - start_time
        print(f"\n✅ Extracted {len(texts)} pages in {processing_time:.2f}s")
        
        return texts, processing_time
    
    def parse_with_unstructured(
        self, 
        pdf_path: str, 
        strategy: str = "hi_res",
        extract_images: bool = False,
        extract_tables: bool = True
    ) -> Tuple[List, float]:
        """
        Parse PDF menggunakan Unstructured library (FULL FEATURES)
        
        Args:
            pdf_path: Path to PDF file
            strategy: Parsing strategy - 'hi_res', 'fast', 'ocr_only', 'auto'
            extract_images: Whether to extract images
            extract_tables: Whether to extract tables
            
        Returns:
            Tuple of (elements, processing_time)
        """
        if not check_unstructured():
            raise ImportError("Unstructured not installed. Run: pip install 'unstructured[pdf]'")
        
        from unstructured.partition.pdf import partition_pdf
        
        print(f"📄 [Unstructured] Parsing: {pdf_path}")
        print(f"   Strategy: {strategy}")
        print(f"   Extract images: {extract_images}")
        print(f"   Extract tables: {extract_tables}")
        start_time = time.time()
        
        # Extract block types
        extract_block_types = []
        if extract_images:
            extract_block_types.append("Image")
        if extract_tables:
            extract_block_types.append("Table")
        
        try:
            # PARAMETER LENGKAP seperti file asli
            elements = partition_pdf(
                filename=pdf_path,
                strategy=strategy,
                languages=["eng", "ind"],   
                # extract_images_in_pdf=extract_images,
                # extract_image_block_types=extract_block_types if extract_block_types else None,
                # extract_image_block_to_payload=False,
                # extract_image_block_output_dir=self.output_dir if extract_images else None,
                extract_images_in_pdf=False,
                extract_image_block_types=["Table"],
                extract_image_block_to_payload=False,
                extract_image_block_output_dir=self.output_dir 
            )
        except Exception as e:
            print(f"⚠️ Error dengan strategy '{strategy}': {e}",flush=True)
            print("🔄 Falling back to 'auto' strategy...",flush=True)
            elements = partition_pdf(
                filename=pdf_path,
                strategy="auto",
                extract_images_in_pdf=extract_images,
                extract_image_block_types=extract_block_types if extract_block_types else None,
                extract_image_block_to_payload=False,
                extract_image_block_output_dir=self.output_dir if extract_images else None,
            )
        
        processing_time = time.time() - start_time
        print(f"✅ Extracted {len(elements)} elements in {processing_time:.2f}s",flush=True)
        print(f"✅ Extracted images saved to: {self.output_dir}" if extract_images else "",flush=True)
        return elements, processing_time
    
    def parse_with_tesseract(self, pdf_path: str) -> Tuple[List[str], float]:
        """
        Parse PDF menggunakan Tesseract OCR
        """
        if not check_tesseract():
            raise ImportError("Tesseract not installed. Run: pip install pytesseract pdf2image")
        
        import pytesseract
        from pdf2image import convert_from_path
        
        print(f"📄 [Tesseract] Parsing: {pdf_path}")
        start_time = time.time()
        
        images = convert_from_path(pdf_path)
        texts = []
        
        lang = self.config.get('lang', 'ind+eng')
        config = self.config.get('config', '--psm 6')
        
        for i, img in enumerate(images, 1):
            print(f"   Processing page {i}/{len(images)}...", end="\r")
            text = pytesseract.image_to_string(img, lang=lang, config=config)
            texts.append(text)
        
        processing_time = time.time() - start_time
        print(f"\n✅ Extracted {len(texts)} pages in {processing_time:.2f}s")
        
        return texts, processing_time
    
    def parse_pdf(self, pdf_path: str) -> Tuple:
        """
        Main parsing method - routes to appropriate OCR method
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Tuple of (elements/texts, processing_time)
        """
        # Get config options
        strategy = self.config.get('strategy', 'hi_res')
        extract_images = self.config.get('extract_images', False)
        extract_tables = self.config.get('extract_tables', True)
        
        if self.ocr_method == OCRMethod.PYMUPDF:
            return self.parse_with_pymupdf(pdf_path)
        elif self.ocr_method == OCRMethod.UNSTRUCTURED:
            return self.parse_with_unstructured(
                pdf_path, 
                strategy=strategy,
                extract_images=extract_images,
                extract_tables=extract_tables
            )
        elif self.ocr_method == OCRMethod.TESSERACT:
            return self.parse_with_tesseract(pdf_path)
        else:
            raise ValueError(f"Unsupported OCR method: {self.ocr_method}")
    
    def categorize_elements(self, elements) -> Dict[str, List[str]]:
        """
        Kategorisasi elemen PDF menjadi tabel, teks, dan gambar
        
        Works for both PyMuPDF (strings) and Unstructured (elements)
        
        IMPORTANT: Menggabungkan semua teks menjadi satu dokumen besar
        agar chunking bisa bekerja dengan baik
        """
        tables = []
        texts = []
        images = []
        
        for el in elements:
            # If it's a string (from PyMuPDF), add to texts
            if isinstance(el, str):
                if el.strip():
                    texts.append(el.strip())
            else:
                # Unstructured elements
                element_type = type(el).__name__
                
                if element_type == "Table":
                    tables.append(str(el))
                elif element_type in ["NarrativeText", "Title", "Text", "ListItem", "Header", "Footer"]:
                    text = str(el).strip()
                    if text:
                        texts.append(text)
                elif element_type == "Image":
                    images.append(str(el))
                else:
                    # Add other elements as text
                    text = str(el).strip()
                    if text:
                        texts.append(text)
        
        # PENTING: Gabungkan semua teks menjadi SATU dokumen besar
        # Ini memastikan chunking bisa memecah dengan benar
        combined_text = "\n\n".join(texts)
        
        output = {
            "tables": tables,
            "texts": [combined_text] if combined_text else [],  # Satu dokumen besar
            "images": images
        }
        
        print(f"📊 Kategorisasi:")
        print(f"   - Tabel: {len(tables)}")
        print(f"   - Teks: {len(texts)} elements -> combined into 1 document ({len(combined_text)} chars)")
        print(f"   - Gambar: {len(images)}")
        
        return output
    
    def get_extracted_images(self) -> List[str]:
        """
        Get list of extracted image paths from output directory
        
        Returns:
            List of image file paths
        """
        image_files = []
        
        if os.path.exists(self.output_dir):
            for f in sorted(os.listdir(self.output_dir)):
                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                    image_files.append(os.path.join(self.output_dir, f))
        
        return image_files
