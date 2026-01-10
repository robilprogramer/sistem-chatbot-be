# ============================================================================
# FILE: utils/metadata_extractor.py
# ============================================================================

import re
from typing import Dict, Optional, List
from pathlib import Path


class MetadataExtractor:
    """
    Extract metadata dari filename dan content dokumen
    
    Metadata yang diextract:
    - jenjang: TK, SD, SMP, SMA, SMK
    - cabang: Cibinong, Bogor, Pulogadung, Kelapa Gading, dll
    - tahun: 2024, 2025, 2026, 2024/2025, dll
    - kategori: biaya, SK, peraturan, panduan, dll
    """
    
    
    def __init__(self, master_repo):
        self.JENJANG_LIST = master_repo.get_jenjang()
        self.CABANG_LIST = master_repo.get_cabang()
        self.KATEGORI_LIST = master_repo.get_kategori()

    def extract_from_filename(self, filename: str) -> Dict[str, Optional[str]]:
        stem = Path(filename).stem
        filename_lower = stem.lower()
        # 🔧 NORMALISASI: underscore & dash → spasi
        normalized = re.sub(r"[_\-]+", " ", filename_lower)
        metadata = {
            "jenjang": None,
            "cabang": None,
            "tahun": None,
            "kategori": None,
            "source": stem,
            "filename": filename
        }

        # === JENJANG ===
        for jenjang in self.JENJANG_LIST:
            if re.search(rf"\b{re.escape(jenjang.lower())}\b", normalized):
                metadata["jenjang"] = jenjang.upper()
                break

        for cabang in self.CABANG_LIST:
            if re.search(rf"\b{re.escape(cabang.lower())}\b", normalized):
                metadata["cabang"] = cabang.title()
                break

        for pattern in [r"20\d{2}/20\d{2}", r"20\d{2}-20\d{2}", r"20\d{2}"]:
            match = re.search(pattern, filename_lower)
            if match:
                metadata["tahun"] = match.group()
                break

        for kategori in self.KATEGORI_LIST:
            if kategori in filename_lower:
                metadata["kategori"] = kategori.title()
                break

        return metadata
    
    def extract_from_content(self, content: str, max_chars: int = 2000) -> Dict:
        text = content[:max_chars].lower()

        metadata = {
            "jenjang": None,
            "cabang": None,
            "tahun": None,
            "kategori": None
        }

        for jenjang in self.JENJANG_LIST:
            if re.search(rf"\b{jenjang.lower()}\b", text):
                metadata["jenjang"] = jenjang
                break

        for cabang in self.CABANG_LIST:
            if re.search(rf"\b{re.escape(cabang)}\b", text):
                metadata["cabang"] = cabang.title()
                break

        for pattern in [r"20\d{2}/20\d{2}", r"20\d{2}-20\d{2}", r"20\d{2}"]:
            match = re.search(pattern, text)
            if match:
                metadata["tahun"] = match.group()
                break

        for kategori in self.KATEGORI_LIST:
            if kategori in text:
                metadata["kategori"] = kategori.title()
                break

        return metadata

    
    def extract_full(self, filename: str, content: str) -> Dict[str, str]:
        f_meta = self.extract_from_filename(filename)
        c_meta = self.extract_from_content(content)

        merged = {}
        for key in ["jenjang", "cabang", "tahun", "kategori"]:
            merged[key] = f_meta.get(key) or c_meta.get(key) or "All"

        merged["source"] = f_meta["source"]
        merged["filename"] = f_meta["filename"]
        return merged
    
    # ------------------------------------------------------------------
    # SEARCH FILTER (CHROMA / VECTOR DB)
    # ------------------------------------------------------------------
    @staticmethod
    def create_search_filter(**kwargs) -> Optional[Dict]:
        return {k: v for k, v in kwargs.items() if v} or None


# ============================================================================
# QUERY PARSER - Parse user query untuk extract filter
# ============================================================================

class QueryParser:
    def __init__(self, extractor: MetadataExtractor):
        self.extractor = extractor

    def parse_query(self, query: str) -> Dict[str, Optional[str]]:
        q = query.lower()

        parsed = {
            "jenjang": None,
            "cabang": None,
            "tahun": None,
            "kategori": None
        }

        for j in self.extractor.JENJANG_LIST:
            if re.search(rf"\b{j.lower()}\b", q):
                parsed["jenjang"] = j
                break

        for c in self.extractor.CABANG_LIST:
            if re.search(rf"\b{re.escape(c)}\b", q):
                parsed["cabang"] = c.title()
                break

        for pattern in [r"20\d{2}/20\d{2}", r"20\d{2}-20\d{2}", r"20\d{2}"]:
            m = re.search(pattern, query)
            if m:
                parsed["tahun"] = m.group()
                break

        keyword_map = {
            "Biaya": ["biaya", "spp", "uang pangkal"],
            "PPDB": ["ppdb", "pendaftaran"],
            "Peraturan": ["peraturan", "aturan"],
            "Panduan": ["panduan", "cara"]
        }

        for k, words in keyword_map.items():
            if any(w in q for w in words):
                parsed["kategori"] = k
                break

        return parsed


