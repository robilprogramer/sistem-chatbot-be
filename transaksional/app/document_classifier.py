"""
Document Classifier - LLM-based Document Type Detection
========================================================
Menggunakan LLM untuk mengklasifikasi jenis dokumen dari:
1. Nama file
2. Konten gambar (jika vision model tersedia)
3. Metadata file

Fitur:
- Auto-detect document type dari nama file
- Vision-based classification untuk gambar
- Batch classification untuk multiple files
"""

import os
import re
import base64
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class DocumentType(str, Enum):
    """Supported document types"""
    AKTA_KELAHIRAN = "akta_kelahiran"
    KARTU_KELUARGA = "kartu_keluarga"
    KTP_ORTU = "ktp_ortu"
    IJAZAH = "ijazah_terakhir"
    RAPOR = "rapor_terakhir"
    FOTO_SISWA = "foto_siswa"
    BUKTI_PEMBAYARAN = "bukti_pembayaran"
    UNKNOWN = "unknown"


@dataclass
class ClassificationResult:
    """Result of document classification"""
    file_path: str
    file_name: str
    original_name: str
    detected_type: DocumentType
    confidence: float  # 0.0 - 1.0
    detection_method: str  # "filename", "vision", "llm"
    suggested_label: str
    
    def to_dict(self) -> Dict:
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "original_name": self.original_name,
            "detected_type": self.detected_type.value,
            "confidence": self.confidence,
            "detection_method": self.detection_method,
            "suggested_label": self.suggested_label
        }


class DocumentClassifier:
    """
    Classifier untuk mendeteksi jenis dokumen secara otomatis.
    """
    
    # Keyword patterns for filename-based detection
    FILENAME_PATTERNS = {
        DocumentType.AKTA_KELAHIRAN: [
            r"akta", r"kelahiran", r"birth", r"akte", r"lahir"
        ],
        DocumentType.KARTU_KELUARGA: [
            r"kk\b", r"kartu.?keluarga", r"family.?card", r"keluarga"
        ],
        DocumentType.KTP_ORTU: [
            r"ktp", r"identitas", r"id.?card", r"nik", r"ortu", r"ayah", r"ibu", r"orang.?tua"
        ],
        DocumentType.IJAZAH: [
            r"ijazah", r"diploma", r"certificate", r"sertifikat", r"lulus", r"kelulusan"
        ],
        DocumentType.RAPOR: [
            r"rapor", r"raport", r"report.?card", r"nilai", r"transkrip"
        ],
        DocumentType.FOTO_SISWA: [
            r"foto", r"photo", r"pas.?foto", r"siswa", r"murid", r"anak", r"profile"
        ],
        DocumentType.BUKTI_PEMBAYARAN: [
            r"bukti", r"bayar", r"payment", r"transfer", r"receipt", r"kwitansi", r"struk"
        ]
    }
    
    # Labels for each document type
    DOCUMENT_LABELS = {
        DocumentType.AKTA_KELAHIRAN: "Akta Kelahiran",
        DocumentType.KARTU_KELUARGA: "Kartu Keluarga",
        DocumentType.KTP_ORTU: "KTP Orang Tua",
        DocumentType.IJAZAH: "Ijazah Terakhir",
        DocumentType.RAPOR: "Rapor Terakhir",
        DocumentType.FOTO_SISWA: "Foto Siswa",
        DocumentType.BUKTI_PEMBAYARAN: "Bukti Pembayaran",
        DocumentType.UNKNOWN: "Dokumen Lainnya"
    }
    
    def __init__(self, llm_client=None):
        """
        Initialize classifier.
        
        Args:
            llm_client: Optional LLM client for advanced classification
        """
        self._llm = llm_client
    
    @property
    def llm(self):
        """Lazy load LLM client"""
        if self._llm is None:
            try:
                from transaksional.app.llm_client import get_llm
                self._llm = get_llm()
            except:
                pass
        return self._llm
    
    def classify_by_filename(self, filename: str) -> Tuple[DocumentType, float]:
        """
        Classify document type based on filename.
        
        Returns: (DocumentType, confidence)
        """
        filename_lower = filename.lower()
        
        # Remove extension and clean
        name_without_ext = Path(filename_lower).stem
        # Replace underscores and hyphens with spaces
        cleaned_name = re.sub(r'[_\-\.]', ' ', name_without_ext)
        
        best_match = DocumentType.UNKNOWN
        best_score = 0.0
        
        for doc_type, patterns in self.FILENAME_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, cleaned_name, re.IGNORECASE):
                    # Calculate confidence based on pattern specificity
                    confidence = 0.7 + (0.1 * len(pattern) / 10)  # Longer patterns = higher confidence
                    confidence = min(confidence, 0.95)
                    
                    if confidence > best_score:
                        best_score = confidence
                        best_match = doc_type
        
        return best_match, best_score
    
    async def classify_by_vision(self, file_path: str) -> Tuple[DocumentType, float]:
        """
        Classify document type using vision/image analysis.
        
        Returns: (DocumentType, confidence)
        """
        if not self.llm:
            return DocumentType.UNKNOWN, 0.0
        
        # Check if file is an image
        ext = Path(file_path).suffix.lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
            return DocumentType.UNKNOWN, 0.0
        
        try:
            # Read and encode image
            with open(file_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            
            # Determine media type
            media_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }
            media_type = media_types.get(ext, 'image/jpeg')
            
            # Create prompt for classification
            prompt = """Analisis gambar dokumen ini dan tentukan jenisnya.

Pilih SATU dari kategori berikut:
1. akta_kelahiran - Akta kelahiran/surat keterangan lahir
2. kartu_keluarga - Kartu Keluarga (KK)
3. ktp_ortu - KTP (Kartu Tanda Penduduk)
4. ijazah_terakhir - Ijazah/sertifikat kelulusan
5. rapor_terakhir - Rapor/buku nilai
6. foto_siswa - Foto pas/foto profil
7. bukti_pembayaran - Bukti transfer/kwitansi
8. unknown - Tidak dapat diidentifikasi

Jawab dalam format JSON:
{"type": "kategori", "confidence": 0.0-1.0, "reason": "alasan singkat"}
"""
            
            # Call LLM with vision
            result = await self.llm.analyze_image(image_data, media_type, prompt)
            
            if result:
                import json
                try:
                    parsed = json.loads(result)
                    doc_type = DocumentType(parsed.get("type", "unknown"))
                    confidence = float(parsed.get("confidence", 0.5))
                    return doc_type, confidence
                except:
                    pass
            
        except Exception as e:
            print(f"Vision classification error: {e}")
        
        return DocumentType.UNKNOWN, 0.0
    
    async def classify_single(self, file_path: str, original_name: str = None,
                             use_vision: bool = True) -> ClassificationResult:
        """
        Classify a single document.
        
        Args:
            file_path: Path to the file
            original_name: Original filename (if different from file_path)
            use_vision: Whether to use vision analysis for images
            
        Returns: ClassificationResult
        """
        filename = original_name or os.path.basename(file_path)
        
        # Try filename-based classification first
        doc_type, confidence = self.classify_by_filename(filename)
        method = "filename"
        
        # If confidence is low and file is an image, try vision
        if confidence < 0.6 and use_vision:
            ext = Path(file_path).suffix.lower()
            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                vision_type, vision_conf = await self.classify_by_vision(file_path)
                
                # Use vision result if better
                if vision_conf > confidence:
                    doc_type = vision_type
                    confidence = vision_conf
                    method = "vision"
        
        return ClassificationResult(
            file_path=file_path,
            file_name=os.path.basename(file_path),
            original_name=filename,
            detected_type=doc_type,
            confidence=confidence,
            detection_method=method,
            suggested_label=self.DOCUMENT_LABELS.get(doc_type, "Dokumen")
        )
    
    async def classify_batch(self, files: List[Dict], use_vision: bool = True) -> List[ClassificationResult]:
        """
        Classify multiple documents at once.
        
        Args:
            files: List of file info dicts with 'file_path' and optionally 'original_name'
            use_vision: Whether to use vision analysis
            
        Returns: List of ClassificationResult
        """
        results = []
        
        for file_info in files:
            file_path = file_info.get("file_path", "")
            original_name = file_info.get("original_name", file_info.get("file_name", ""))
            
            result = await self.classify_single(file_path, original_name, use_vision)
            results.append(result)
        
        return results
    
    async def classify_and_group(self, files: List[Dict], 
                                  use_vision: bool = True) -> Dict[str, List[ClassificationResult]]:
        """
        Classify files and group by document type.
        
        Returns: Dict mapping document type to list of files
        """
        results = await self.classify_batch(files, use_vision)
        
        grouped = {}
        for result in results:
            doc_type = result.detected_type.value
            if doc_type not in grouped:
                grouped[doc_type] = []
            grouped[doc_type].append(result)
        
        return grouped
    
    def get_field_id_for_type(self, doc_type: DocumentType) -> str:
        """Map document type to form field ID"""
        mapping = {
            DocumentType.AKTA_KELAHIRAN: "akta_kelahiran",
            DocumentType.KARTU_KELUARGA: "kartu_keluarga",
            DocumentType.KTP_ORTU: "ktp_ortu",
            DocumentType.IJAZAH: "ijazah_terakhir",
            DocumentType.RAPOR: "rapor_terakhir",
            DocumentType.FOTO_SISWA: "foto_siswa",
            DocumentType.BUKTI_PEMBAYARAN: "bukti_pembayaran",
        }
        return mapping.get(doc_type, "document")


# Singleton
_classifier: Optional[DocumentClassifier] = None

def get_document_classifier() -> DocumentClassifier:
    global _classifier
    if _classifier is None:
        _classifier = DocumentClassifier()
    return _classifier