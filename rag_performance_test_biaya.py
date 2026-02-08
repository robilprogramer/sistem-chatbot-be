"""
================================================================================
RAG PERFORMANCE TESTING - FOKUS QUERY BIAYA SEKOLAH
================================================================================
Script untuk mengukur performa RAG khusus query informational tentang biaya:
- SmartRetriever (informasional/utils/smart_retriever.py)
- QueryChain (informasional/core/rag_factory.py)

Dataset Query: 40 Query Informational
- A. Query Biaya Sekolah (15 query)
- B. Query Biaya Formulir/Pendaftaran (9 query)
- C. Query Syarat Pendaftaran (1 query)
- D. Query Uang Pangkal (15 query)

Rubrik Relevansi (0-2): 
- 0 = Tidak Relevan
- 1 = Cukup Relevan
- 2 = Sangat Relevan

Scoring Modes:
- lenient: Mudah dapat nilai tinggi (untuk debugging)
- moderate: Balanced (untuk testing awal)
- strict: Ketat dan realistis (untuk penelitian/publikasi)

Metrik: Precision@k, Recall@k untuk k=1,3,5

USAGE:
    # Run semua pengujian
    python rag_performance_test_biaya.py --config path/to/config.yaml
    
    # Retrieval only
    python rag_performance_test_biaya.py --config config.yaml --retrieval-only
    
    # Response quality only  
    python rag_performance_test_biaya.py --config config.yaml --response-only
    
    # Manual judgement mode
    python rag_performance_test_biaya.py --config config.yaml --manual

Author: [Nama Mahasiswa]
Version: 3.0 - Query Set Biaya Sekolah (Informational Only)
================================================================================
"""

import sys
import os
import time
import argparse
import json
import csv
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from enum import Enum

# Import modules RAG Anda
try:
    from informasional.utils.smart_retriever import get_smart_retriever, reset_smart_retriever
    from informasional.core.rag_factory import get_query_chain, reset_query_chain
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Warning: Could not import RAG modules: {e}")
    print("   Script will run in demo mode with simulated results.")
    MODULES_AVAILABLE = False


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Konfigurasi pengujian"""
    DEFAULT_CONFIG_PATH = "informasional/config/config.yaml"
    OUTPUT_DIR = "hasil_pengujian_rag_biaya"
    
    # Retrieval settings
    TOP_K = 5  # Maximum chunks to retrieve
    K_VALUES = [1, 3, 5]  # k values for Precision@k and Recall@k
    
    # Relevance threshold
    RELEVANCE_THRESHOLD = 1  # Score >= 1 dianggap relevan
    
    # Response quality thresholds
    QUALITY_THRESHOLD = 4.0  # Target average score
    
    # Scoring strictness: "lenient", "moderate", "strict"
    SCORING_MODE = "strict"  # Default: strict (lebih realistis)
    
    # Strict mode thresholds
    STRICT_SIMILARITY_HIGH = 0.80  # For score 2
    STRICT_SIMILARITY_MED = 0.70   # For score 1
    STRICT_KEYWORDS_HIGH = 5       # For score 2
    STRICT_KEYWORDS_MED = 3        # For score 1


# ============================================================================
# QUERY SETS - 40 QUERY INFORMATIONAL (FOKUS BIAYA SEKOLAH)
# ============================================================================

# A. Query Biaya Sekolah (15 Query)
QUERY_BIAYA_SEKOLAH = [
    {
        "id": "Q-A01",
        "query": "Berapa jumlah SMA ",
        "category": "informasi",
        "subcategory": "informasi",
        "jenjang": "SMA",
        "cabang": "kosong",
        "expected_topics": ["informasi", "2025", "tahun ajaran"]
    },
    {
        "id": "Q-A02",
        "query": "Rincian biaya masuk SD Islam Al Azhar 1 Kebayoran Baru tahun 2026–2027 apa saja?",
        "category": "biaya_sekolah",
        "subcategory": "biaya_masuk",
        "jenjang": "SD",
        "cabang": "Al Azhar 1 Kebayoran Baru",
        "expected_topics": ["rincian", "biaya", "masuk", "sd", "kebayoran baru", "2026"]
    },
    {
        "id": "Q-A03",
        "query": "Berapa biaya pendidikan TK Islam Al Azhar 17 Bintaro tahun 2026?",
        "category": "biaya_sekolah",
        "subcategory": "biaya_pendidikan",
        "jenjang": "TK",
        "cabang": "Al Azhar 17 Bintaro",
        "expected_topics": ["biaya", "pendidikan", "tk", "bintaro", "2026"]
    },
    {
        "id": "Q-A04",
        "query": "Berapa total biaya sekolah",
        "category": "biaya_sekolah",
        "subcategory": "total_biaya",
        "jenjang": "TK",
        "cabang": "Al Azhar 2 Pasar Minggu",
        "expected_topics": ["total", "biaya", "sekolah", "tk", "pasar minggu", "2026"]
    },
    {
        "id": "Q-A05",
        "query": "Biaya pendidikan TK Islam Al Azhar 51 Sidoarjo tahun ajaran 2026 berapa?",
        "category": "biaya_sekolah",
        "subcategory": "biaya_pendidikan",
        "jenjang": "TK",
        "cabang": "Al Azhar 51 Sidoarjo",
        "expected_topics": ["biaya", "pendidikan", "tk", "sidoarjo", "2026"]
    },
    {
        "id": "Q-A06",
        "query": "Berapa biaya masuk TK Islam Al Azhar 6 Sentra Primer tahun 2026–2027?",
        "category": "biaya_sekolah",
        "subcategory": "biaya_masuk",
        "jenjang": "TK",
        "cabang": "Al Azhar 6 Sentra Primer",
        "expected_topics": ["biaya", "masuk", "tk", "sentra primer", "2026"]
    },
    {
        "id": "Q-A07",
        "query": "Rincian biaya SMP Islam Al Azhar tahun 2026 apa saja?",
        "category": "biaya_sekolah",
        "subcategory": "rincian_biaya",
        "jenjang": "SMP",
        "cabang": "Umum",
        "expected_topics": ["rincian", "biaya", "smp", "al azhar", "2026"]
    },
    {
        "id": "Q-A08",
        "query": "Berapa biaya penerimaan murid baru SD Islam Al Azhar 36 Bandung?",
        "category": "biaya_sekolah",
        "subcategory": "biaya_pmb",
        "jenjang": "SD",
        "cabang": "Al Azhar 36 Bandung",
        "expected_topics": ["biaya", "penerimaan", "murid baru", "pmb", "sd", "bandung"]
    },
    {
        "id": "Q-A09",
        "query": "Apa saja komponen biaya sekolah SD Al Azhar 27 Cibinong?",
        "category": "biaya_sekolah",
        "subcategory": "komponen_biaya",
        "jenjang": "SD",
        "cabang": "Al Azhar 27 Cibinong",
        "expected_topics": ["komponen", "biaya", "sekolah", "sd", "cibinong"]
    },
    {
        "id": "Q-A10",
        "query": "Biaya tahunan SD Al Azhar Kebayoran Baru tahun 2026 berapa?",
        "category": "biaya_sekolah",
        "subcategory": "biaya_tahunan",
        "jenjang": "SD",
        "cabang": "Al Azhar Kebayoran Baru",
        "expected_topics": ["biaya", "tahunan", "sd", "kebayoran baru", "2026"]
    },
    {
        "id": "Q-A11",
        "query": "Berapa uang sekolah per bulan TK Al Azhar 17 Bintaro?",
        "category": "biaya_sekolah",
        "subcategory": "spp_bulanan",
        "jenjang": "TK",
        "cabang": "Al Azhar 17 Bintaro",
        "expected_topics": ["uang sekolah", "spp", "bulanan", "tk", "bintaro"]
    },
    {
        "id": "Q-A12",
        "query": "Biaya pendidikan TK Al Azhar Pasar Minggu meliputi apa saja?",
        "category": "biaya_sekolah",
        "subcategory": "komponen_biaya",
        "jenjang": "TK",
        "cabang": "Al Azhar Pasar Minggu",
        "expected_topics": ["biaya", "pendidikan", "meliputi", "komponen", "tk", "pasar minggu"]
    },
    {
        "id": "Q-A13",
        "query": "Apakah biaya TK Al Azhar JAWAB BARAT sudah termasuk seragam?",
        "category": "biaya_sekolah",
        "subcategory": "inklusif_biaya",
        "jenjang": "TK",
        "cabang": "JAWAB BARAT",
        "expected_topics": ["biaya", "termasuk", "seragam", "tk", "JAWAB BARAT"]
    },
    {
        "id": "Q-A14",
        "query": "Rincian biaya SMP Al Azhar tahun ajaran terbaru?",
        "category": "biaya_sekolah",
        "subcategory": "rincian_biaya",
        "jenjang": "SMP",
        "cabang": "Umum",
        "expected_topics": ["rincian", "biaya", "smp", "al azhar", "terbaru"]
    },
    {
        "id": "Q-A15",
        "query": "Berapa biaya uang pangkal dan uang sekolah TK A di Al Azhar 27 Cibinong tahun ajaran 2026/2027?",
        "category": "biaya_sekolah",
        "subcategory": "total_biaya_masuk",
        "jenjang": "SD",
        "cabang": "Al Azhar 27 Cibinong",
        "expected_topics": ["total", "biaya", "masuk", "sd", "27 Cibinong", "2026"]
    },
]

# B. Query Biaya Formulir/Pendaftaran (9 Query)
QUERY_BIAYA_FORMULIR = [
    {
        "id": "Q-B01",
        "query": "Berapa biaya formulir pendaftaran SD Al Azhar 27 Cibinong?",
        "category": "biaya_formulir",
        "subcategory": "biaya_formulir",
        "jenjang": "SD",
        "cabang": "Al Azhar 27 Cibinong",
        "expected_topics": ["biaya", "formulir", "pendaftaran", "sd", "cibinong"]
    },
    {
        "id": "Q-B02",
        "query": "Biaya pendaftaran SD Al Azhar Kebayoran Baru tahun 2026 berapa?",
        "category": "biaya_formulir",
        "subcategory": "biaya_pendaftaran",
        "jenjang": "SD",
        "cabang": "Al Azhar Kebayoran Baru",
        "expected_topics": ["biaya", "pendaftaran", "sd", "kebayoran baru", "2026"]
    },
    {
        "id": "Q-B03",
        "query": "Apakah pendaftaran TK Al Azhar 17 Bintaro dikenakan biaya?",
        "category": "biaya_formulir",
        "subcategory": "ada_biaya",
        "jenjang": "TK",
        "cabang": "Al Azhar 17 Bintaro",
        "expected_topics": ["pendaftaran", "dikenakan", "biaya", "tk", "bintaro"]
    },
    {
        "id": "Q-B04",
        "query": "Berapa biaya pendaftaran siswa baru SD Al Azhar Bandung?",
        "category": "biaya_formulir",
        "subcategory": "biaya_pendaftaran",
        "jenjang": "SD",
        "cabang": "Al Azhar Bandung",
        "expected_topics": ["biaya", "pendaftaran", "siswa baru", "sd", "bandung"]
    },
    {
        "id": "Q-B05",
        "query": "Biaya administrasi pendaftaran TK Al Azhar Pasar Minggu berapa?",
        "category": "biaya_formulir",
        "subcategory": "biaya_administrasi",
        "jenjang": "TK",
        "cabang": "Al Azhar Pasar Minggu",
        "expected_topics": ["biaya", "administrasi", "pendaftaran", "tk", "pasar minggu"]
    },
    {
        "id": "Q-B06",
        "query": "Apakah formulir pendaftaran Al Azhar gratis?",
        "category": "biaya_formulir",
        "subcategory": "gratis_berbayar",
        "jenjang": "Umum",
        "cabang": "Umum",
        "expected_topics": ["formulir", "pendaftaran", "gratis", "al azhar"]
    },
    {
        "id": "Q-B07",
        "query": "Berapa biaya daftar ulang SD Al Azhar?",
        "category": "biaya_formulir",
        "subcategory": "biaya_daftar_ulang",
        "jenjang": "SD",
        "cabang": "Umum",
        "expected_topics": ["biaya", "daftar ulang", "sd", "al azhar"]
    },
    {
        "id": "Q-B08",
        "query": "Biaya pendaftaran online Al Azhar berapa?",
        "category": "biaya_formulir",
        "subcategory": "biaya_online",
        "jenjang": "Umum",
        "cabang": "Umum",
        "expected_topics": ["biaya", "pendaftaran", "online", "al azhar"]
    },
    {
        "id": "Q-B09",
        "query": "Rincian biaya pendaftaran",
        "category": "rincian",
        "subcategory": "rincian_biaya_pendaftaran",
        "jenjang": "sd",
        "cabang": "sd",
        "expected_topics": ["rincian", "biaya", "ssss", "siswa baru", "al ssazhar"]
    },
]

# C. Query Syarat Pendaftaran (1 Query)
QUERY_SYARAT = [
    {
        "id": "Q-C01",
        "query": "Apa saja dokumen yang dibutuhkan?",
        "category": "syarat_pendaftaran",
        "subcategory": "dokumen_persyaratan",
        "jenjang": "SD",
        "cabang": "Umum",
        "expected_topics": ["dokumen", "persyaratan", "pendaftaran", "sd", "al azhar"]
    },
]

# D. Query Uang Pangkal (15 Query)
QUERY_UANG_PANGKAL = [
    {
        "id": "Q-D01",
        "query": "Berapa uang pangkal SD Al Azhar 27 Cibinong?",
        "category": "uang_pangkal",
        "subcategory": "nominal_pangkal",
        "jenjang": "SD",
        "cabang": "Al Azhar 27 Cibinong",
        "expected_topics": ["uang pangkal", "sd", "cibinong", "al azhar"]
    },
    {
        "id": "Q-D02",
        "query": "Uang pangkal SD Al Azhar Kebayoran Baru tahun 2026 berapa?",
        "category": "uang_pangkal",
        "subcategory": "nominal_pangkal",
        "jenjang": "SD",
        "cabang": "Al Azhar Kebayoran Baru",
        "expected_topics": ["uang pangkal", "sd", "kebayoran baru", "2026"]
    },
    {
        "id": "Q-D03",
        "query": "Apakah TK Al Azhar 17 Bintaro memiliki uang pangkal?",
        "category": "uang_pangkal",
        "subcategory": "ada_pangkal",
        "jenjang": "TK",
        "cabang": "Al Azhar 17 Bintaro",
        "expected_topics": ["uang pangkal", "tk", "bintaro", "memiliki"]
    },
    {
        "id": "Q-D04",
        "query": "Berapa uang pangkal masuk TK Al Azhar Pasar Minggu?",
        "category": "uang_pangkal",
        "subcategory": "nominal_pangkal",
        "jenjang": "TK",
        "cabang": "Al Azhar Pasar Minggu",
        "expected_topics": ["uang pangkal", "masuk", "tk", "pasar minggu"]
    },
    {
        "id": "Q-D05",
        "query": "Uang pangkal SD Al Azhar Bandung berapa?",
        "category": "uang_pangkal",
        "subcategory": "nominal_pangkal",
        "jenjang": "SD",
        "cabang": "Al Azhar Bandung",
        "expected_topics": ["uang pangkal", "sd", "bandung"]
    },
    {
        "id": "Q-D06",
        "query": "Rincian uang pangkal TK Al Azhar Sidoarjo?",
        "category": "uang_pangkal",
        "subcategory": "rincian_pangkal",
        "jenjang": "TK",
        "cabang": "Al Azhar Sidoarjo",
        "expected_topics": ["rincian", "uang pangkal", "tk", "sidoarjo"]
    },
    {
        "id": "Q-D07",
        "query": "Apakah uang pangkal bisa dicicil di Al Azhar?",
        "category": "uang_pangkal",
        "subcategory": "sistem_bayar",
        "jenjang": "Umum",
        "cabang": "Umum",
        "expected_topics": ["uang pangkal", "dicicil", "al azhar", "pembayaran"]
    },
    {
        "id": "Q-D08",
        "query": "Berapa biaya uang gedung SD Al Azhar?",
        "category": "uang_pangkal",
        "subcategory": "uang_gedung",
        "jenjang": "SD",
        "cabang": "Umum",
        "expected_topics": ["biaya", "uang gedung", "sd", "al azhar"]
    },
    {
        "id": "Q-D09",
        "query": "Uang pangkal SMP Al Azhar tahun ajaran 2026?",
        "category": "uang_pangkal",
        "subcategory": "nominal_pangkal",
        "jenjang": "SMP",
        "cabang": "Umum",
        "expected_topics": ["uang pangkal", "smp", "al azhar", "2026"]
    },
    {
        "id": "Q-D10",
        "query": "Apakah uang pangkal berbeda tiap cabang Al Azhar?",
        "category": "uang_pangkal",
        "subcategory": "perbedaan_cabang",
        "jenjang": "Umum",
        "cabang": "Umum",
        "expected_topics": ["uang pangkal", "berbeda", "cabang", "al azhar"]
    },
    {
        "id": "Q-D11",
        "query": "Sistem pembayaran uang pangkal Al Azhar bagaimana?",
        "category": "uang_pangkal",
        "subcategory": "sistem_bayar",
        "jenjang": "Umum",
        "cabang": "Umum",
        "expected_topics": ["sistem", "pembayaran", "uang pangkal", "al azhar"]
    },
    {
        "id": "Q-D12",
        "query": "Uang pangkal TK Al Azhar Sentra Primer berapa?",
        "category": "uang_pangkal",
        "subcategory": "nominal_pangkal",
        "jenjang": "TK",
        "cabang": "Al Azhar Sentra Primer",
        "expected_topics": ["uang pangkal", "tk", "sentra primer"]
    },
    {
        "id": "Q-D13",
        "query": "Apakah uang pangkal sudah termasuk fasilitas sekolah?",
        "category": "uang_pangkal",
        "subcategory": "inklusif_fasilitas",
        "jenjang": "Umum",
        "cabang": "Umum",
        "expected_topics": ["uang pangkal", "termasuk", "fasilitas", "sekolah"]
    },
    {
        "id": "Q-D14",
        "query": "Biaya awal masuk SD Al Azhar terdiri dari apa saja?",
        "category": "uang_pangkal",
        "subcategory": "komponen_biaya_awal",
        "jenjang": "SD",
        "cabang": "Umum",
        "expected_topics": ["biaya awal", "masuk", "terdiri", "sd", "al azhar"]
    },
    {
        "id": "Q-D15",
        "query": "Total uang pangkal dan biaya masuk SD Al Azhar berapa?",
        "category": "uang_pangkal",
        "subcategory": "total_biaya_awal",
        "jenjang": "SD",
        "cabang": "Umum",
        "expected_topics": ["total", "uang pangkal", "biaya masuk", "sd", "al azhar"]
    },
]

# Gabungkan semua query (INFORMATIONAL ONLY - 40 query)
ALL_INFORMATIONAL_QUERIES = (
    QUERY_BIAYA_SEKOLAH +
    QUERY_BIAYA_FORMULIR +
    QUERY_SYARAT +
    QUERY_UANG_PANGKAL
)


# ============================================================================
# DATA CLASSES
# ============================================================================

class RelevanceScore(Enum):
    """Rubrik Penilaian Relevansi"""
    TIDAK_RELEVAN = 0      # Chunk tidak berkaitan dengan query
    CUKUP_RELEVAN = 1      # Chunk terkait tapi tidak langsung menjawab
    SANGAT_RELEVAN = 2     # Chunk langsung menjawab query secara spesifik


@dataclass
class ChunkEvaluation:
    """Evaluasi per chunk"""
    chunk_id: str
    content_preview: str
    similarity_score: float
    relevance_score: int  # 0, 1, atau 2
    source_document: str = ""
    metadata: Dict = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """Hasil pengujian retrieval untuk satu query"""
    query_id: str
    query: str
    category: str
    subcategory: str = ""
    jenjang: str = ""
    cabang: str = ""
    
    # Retrieved chunks
    chunks: List[ChunkEvaluation] = field(default_factory=list)
    total_retrieved: int = 0
    
    # Relevance counts
    sangat_relevan_count: int = 0  # score = 2
    cukup_relevan_count: int = 0   # score = 1
    tidak_relevan_count: int = 0   # score = 0
    
    # Metrics
    precision_at_1: float = 0.0
    precision_at_3: float = 0.0
    precision_at_5: float = 0.0
    recall_at_1: float = 0.0
    recall_at_3: float = 0.0
    recall_at_5: float = 0.0
    
    # Performance
    response_time: float = 0.0
    
    # Error handling
    error: Optional[str] = None


@dataclass
class ResponseQualityResult:
    """Hasil pengujian response quality"""
    query_id: str
    query: str
    category: str
    
    # Response
    answer: str = ""
    answer_length: int = 0
    sources_count: int = 0
    
    # Quality scores (1-5)
    relevance: int = 0      # Sejauh mana respons menjawab pertanyaan
    accuracy: int = 0       # Kebenaran informasi dibanding knowledge base
    completeness: int = 0   # Kelengkapan informasi
    average: float = 0.0
    
    # Metadata
    avg_similarity: float = 0.0
    response_time: float = 0.0
    
    # Error
    error: Optional[str] = None


# ============================================================================
# RELEVANCE SCORING
# ============================================================================

def auto_score_relevance(
    chunk_content: str,
    chunk_metadata: Dict,
    query: str,
    expected_topics: List[str],
    query_jenjang: str = "",
    query_cabang: str = "",
    scoring_mode: str = "strict"
) -> int:
    """
    Auto-scoring relevansi dengan 3 mode berbeda.
    
    Args:
        scoring_mode: "lenient", "moderate", atau "strict"
    
    Returns:
        int: 0, 1, atau 2
    """
    content_lower = chunk_content.lower()
    query_lower = query.lower()
    
    # Count keyword matches
    keyword_matches = 0
    for topic in expected_topics:
        if topic.lower() in content_lower:
            keyword_matches += 1
    
    # Get similarity score from metadata
    similarity = chunk_metadata.get("similarity_score", 0)
    
    # Check if chunk contains numbers (for biaya queries)
    has_numbers = any(char.isdigit() for char in chunk_content)
    
    # Check for specific cost-related terms
    cost_terms = ["rp", "rupiah", "ribu", "juta", "biaya", "uang", "bayar", "tarif"]
    has_cost_info = any(term in content_lower for term in cost_terms)
    
    # Check jenjang and cabang matching
    chunk_jenjang = chunk_metadata.get("jenjang", "").lower()
    chunk_source = chunk_metadata.get("source", "").lower()
    
    jenjang_match = False
    if query_jenjang and query_jenjang.lower() != "umum":
        jenjang_match = query_jenjang.lower() in chunk_jenjang or query_jenjang.lower() in chunk_source
    
    cabang_match = False
    if query_cabang and query_cabang.lower() != "umum":
        cabang_keywords = query_cabang.lower().split()
        cabang_match = any(kw in chunk_source for kw in cabang_keywords if len(kw) > 3)
    
    # ========================================================================
    # MODE 1: STRICT (Default untuk penelitian)
    # ========================================================================
    if scoring_mode == "strict":
        # Score 2: Butuh bukti sangat kuat
        if has_numbers and has_cost_info and \
           ((keyword_matches >= 5 and similarity >= 0.80) or \
            (jenjang_match and cabang_match and keyword_matches >= 4 and similarity >= 0.75)):
            return 2
        
        # Score 1: Ada relevansi tapi tidak lengkap
        elif (keyword_matches >= 3 and similarity >= 0.70) or \
             (jenjang_match and keyword_matches >= 3 and similarity >= 0.65) or \
             (has_cost_info and keyword_matches >= 2 and similarity >= 0.75):
            return 1
        
        # Score 0: Tidak cukup bukti
        else:
            return 0
    
    # ========================================================================
    # MODE 2: MODERATE (Balanced)
    # ========================================================================
    elif scoring_mode == "moderate":
        # Score 2
        if has_cost_info and \
           ((keyword_matches >= 4 and similarity >= 0.75) or \
            (jenjang_match and cabang_match and keyword_matches >= 3 and similarity >= 0.70)):
            return 2
        
        # Score 1
        elif (keyword_matches >= 2 and similarity >= 0.65) or \
             (jenjang_match and keyword_matches >= 2 and similarity >= 0.60):
            return 1
        
        # Score 0
        else:
            return 0
    
    # ========================================================================
    # MODE 3: LENIENT (Mudah dapat nilai tinggi - untuk debugging)
    # ========================================================================
    else:  # lenient
        # Score 2
        if (keyword_matches >= 3 and similarity >= 0.70) or \
           (jenjang_match and keyword_matches >= 2 and similarity >= 0.65):
            return 2
        
        # Score 1
        elif keyword_matches >= 1 or similarity >= 0.55:
            return 1
        
        # Score 0
        else:
            return 0


def manual_score_relevance(
    chunk_content: str,
    chunk_metadata: Dict,
    query: str,
    chunk_index: int
) -> int:
    """Manual scoring - meminta input dari evaluator."""
    print(f"\n{'─'*70}")
    print(f"📄 Chunk {chunk_index + 1}")
    print(f"{'─'*70}")
    print(f"Query: {query}")
    print(f"\nContent Preview:")
    preview = chunk_content[:400] if len(chunk_content) > 400 else chunk_content
    print(f"  {preview}...")
    print(f"\nSimilarity: {chunk_metadata.get('similarity_score', 'N/A')}")
    print(f"Source: {chunk_metadata.get('source', 'N/A')}")
    print(f"Jenjang: {chunk_metadata.get('jenjang', 'N/A')}")
    print(f"\n{'─'*70}")
    print("Rubrik Penilaian:")
    print("  2 = Sangat Relevan (langsung menjawab query, ada angka/rincian biaya)")
    print("  1 = Cukup Relevan (terkait biaya tapi tidak spesifik ke query)")
    print("  0 = Tidak Relevan (tidak membahas topik yang ditanyakan)")
    print(f"{'─'*70}")
    
    while True:
        try:
            score = int(input("Skor (0/1/2): ").strip())
            if score in [0, 1, 2]:
                return score
            print("❌ Masukkan 0, 1, atau 2!")
        except ValueError:
            print("❌ Input tidak valid!")
        except KeyboardInterrupt:
            print("\n⚠️  Scoring interrupted. Using 0.")
            return 0


# ============================================================================
# METRICS CALCULATION
# ============================================================================

def calculate_precision_at_k(relevance_scores: List[int], k: int, threshold: int = 1) -> float:
    """Hitung Precision@k"""
    if k <= 0:
        return 0.0
    
    scores_at_k = relevance_scores[:min(k, len(relevance_scores))]
    if not scores_at_k:
        return 0.0
    
    relevant_count = sum(1 for s in scores_at_k if s >= threshold)
    return relevant_count / k


def calculate_recall_at_k(
    relevance_scores: List[int], 
    k: int, 
    total_relevant: int,
    threshold: int = 1
) -> float:
    """Hitung Recall@k"""
    if total_relevant <= 0:
        return 0.0
    
    scores_at_k = relevance_scores[:min(k, len(relevance_scores))]
    relevant_in_k = sum(1 for s in scores_at_k if s >= threshold)
    
    return relevant_in_k / total_relevant


# ============================================================================
# RETRIEVAL TESTING
# ============================================================================

class RetrievalTester:
    """Kelas untuk pengujian Retrieval Accuracy"""
    
    def __init__(self, config_path: str, manual_mode: bool = False):
        self.config_path = config_path
        self.manual_mode = manual_mode
        self.retriever = None
        self.results: List[RetrievalResult] = []
        
    def initialize(self):
        """Initialize SmartRetriever"""
        if MODULES_AVAILABLE:
            print("\n🔧 Initializing SmartRetriever...")
            self.retriever = get_smart_retriever(self.config_path)
            
            # Get collection info
            info = self.retriever.get_collection_info()
            print(f"   ✓ Total Vectors: {info.get('total_vectors', 0)}")
            print(f"   ✓ Unique Documents: {info.get('unique_documents', 0)}")
            print(f"   ✓ Embedding Model: {info.get('embedding_model', 'N/A')}")
        else:
            print("\n⚠️  Running in DEMO mode (modules not available)")
    
    def evaluate_query(self, query_data: Dict) -> RetrievalResult:
        """Evaluasi satu query"""
        query_id = query_data["id"]
        query = query_data["query"]
        category = query_data["category"]
        subcategory = query_data.get("subcategory", "")
        jenjang = query_data.get("jenjang", "")
        cabang = query_data.get("cabang", "")
        expected_topics = query_data.get("expected_topics", [])
        
        result = RetrievalResult(
            query_id=query_id,
            query=query,
            category=category,
            subcategory=subcategory,
            jenjang=jenjang,
            cabang=cabang
        )
        
        try:
            # Retrieve chunks
            start_time = time.time()
            
            if MODULES_AVAILABLE and self.retriever:
                docs = self.retriever.retrieve(
                    query=query,
                    filter=None,
                    verbose=False
                )
            else:
                # Demo mode - simulate results
                docs = self._simulate_retrieval(query)
            
            result.response_time = time.time() - start_time
            result.total_retrieved = len(docs)
            
            # Evaluate each chunk
            relevance_scores = []
            
            for i, doc in enumerate(docs[:Config.TOP_K]):
                # Extract content and metadata
                if hasattr(doc, 'page_content'):
                    content = doc.page_content
                    metadata = doc.metadata
                else:
                    content = str(doc.get("content", doc))
                    metadata = doc.get("metadata", {})
                
                # Score relevance
                if self.manual_mode:
                    score = manual_score_relevance(content, metadata, query, i)
                else:
                    score = auto_score_relevance(
                        content, metadata, query, expected_topics,
                        query_jenjang=jenjang,
                        query_cabang=cabang,
                        scoring_mode=Config.SCORING_MODE
                    )
                
                relevance_scores.append(score)
                
                # Create chunk evaluation
                chunk_eval = ChunkEvaluation(
                    chunk_id=metadata.get("chunk_id", f"chunk-{i}"),
                    content_preview=content[:200],
                    similarity_score=metadata.get("similarity_score", 0),
                    relevance_score=score,
                    source_document=metadata.get("source", ""),
                    metadata=metadata
                )
                result.chunks.append(chunk_eval)
                
                # Count by score
                if score == 2:
                    result.sangat_relevan_count += 1
                elif score == 1:
                    result.cukup_relevan_count += 1
                else:
                    result.tidak_relevan_count += 1
            
            # Calculate total relevant (for recall)
            total_relevant = result.sangat_relevan_count + result.cukup_relevan_count
            if total_relevant == 0:
                total_relevant = 1  # Assume at least 1 relevant exists
            
            # Calculate metrics
            result.precision_at_1 = calculate_precision_at_k(relevance_scores, 1)
            result.precision_at_3 = calculate_precision_at_k(relevance_scores, 3)
            result.precision_at_5 = calculate_precision_at_k(relevance_scores, 5)
            
            result.recall_at_1 = calculate_recall_at_k(relevance_scores, 1, total_relevant)
            result.recall_at_3 = calculate_recall_at_k(relevance_scores, 3, total_relevant)
            result.recall_at_5 = calculate_recall_at_k(relevance_scores, 5, total_relevant)
            
        except Exception as e:
            result.error = str(e)
            print(f"   ❌ Error evaluating {query_id}: {e}")
        
        return result
    
    def _simulate_retrieval(self, query: str) -> List[Dict]:
        """Simulate retrieval for demo mode"""
        return [
            {
                "content": f"Simulated chunk {i} for query: {query[:50]}...", 
                "metadata": {
                    "similarity_score": 0.9 - i*0.1,
                    "source": f"biaya_sd_azhar_{i}.pdf",
                    "jenjang": "SD",
                    "chunk_id": f"sim-{i}"
                }
            }
            for i in range(5)
        ]
    
    def run_all_tests(self) -> List[RetrievalResult]:
        """Jalankan semua pengujian retrieval"""
        print("\n" + "="*70)
        print("📊 PENGUJIAN RETRIEVAL ACCURACY - QUERY BIAYA SEKOLAH")
        print("="*70)
        print(f"Total Query: {len(ALL_INFORMATIONAL_QUERIES)} (Informational Only)")
        
        self.initialize()
        
        # Group by category for better organization
        categories = {
            "biaya_sekolah": ("A", QUERY_BIAYA_SEKOLAH),
            "biaya_formulir": ("B", QUERY_BIAYA_FORMULIR),
            "syarat_pendaftaran": ("C", QUERY_SYARAT),
            "uang_pangkal": ("D", QUERY_UANG_PANGKAL),
        }
        
        for cat_key, (cat_label, queries) in categories.items():
            if not queries:
                continue
                
            print(f"\n{'─'*70}")
            print(f"📁 Kategori {cat_label}: {cat_key.replace('_', ' ').title()} (n={len(queries)})")
            print(f"{'─'*70}")
            
            for i, q_data in enumerate(queries, 1):
                print(f"\n[{i}/{len(queries)}] {q_data['id']}: {q_data['query'][:60]}...")
                result = self.evaluate_query(q_data)
                self.results.append(result)
                
                if result.error:
                    print(f"   ❌ Error: {result.error}")
                else:
                    print(f"   ✓ P@3={result.precision_at_3:.0%}, R@3={result.recall_at_3:.0%}, "
                          f"SR={result.sangat_relevan_count}, CR={result.cukup_relevan_count}, "
                          f"Time={result.response_time:.3f}s")
        
        return self.results
    
    def get_summary(self) -> Dict:
        """Hitung ringkasan metrik by category"""
        valid_results = [r for r in self.results if not r.error]
        
        def get_category_stats(category: str):
            cat_results = [r for r in valid_results if r.category == category]
            if not cat_results:
                return None
            
            def avg(values):
                return sum(values) / len(values) if values else 0
            
            return {
                "count": len(cat_results),
                "precision_at_1": avg([r.precision_at_1 for r in cat_results]),
                "precision_at_3": avg([r.precision_at_3 for r in cat_results]),
                "precision_at_5": avg([r.precision_at_5 for r in cat_results]),
                "recall_at_1": avg([r.recall_at_1 for r in cat_results]),
                "recall_at_3": avg([r.recall_at_3 for r in cat_results]),
                "recall_at_5": avg([r.recall_at_5 for r in cat_results]),
                "avg_time": avg([r.response_time for r in cat_results]),
            }
        
        def avg(values):
            return sum(values) / len(values) if values else 0
        
        summary = {
            "biaya_sekolah": get_category_stats("biaya_sekolah"),
            "biaya_formulir": get_category_stats("biaya_formulir"),
            "syarat_pendaftaran": get_category_stats("syarat_pendaftaran"),
            "uang_pangkal": get_category_stats("uang_pangkal"),
            "total": {
                "count": len(valid_results),
                "precision_at_1": avg([r.precision_at_1 for r in valid_results]),
                "precision_at_3": avg([r.precision_at_3 for r in valid_results]),
                "precision_at_5": avg([r.precision_at_5 for r in valid_results]),
                "recall_at_1": avg([r.recall_at_1 for r in valid_results]),
                "recall_at_3": avg([r.recall_at_3 for r in valid_results]),
                "recall_at_5": avg([r.recall_at_5 for r in valid_results]),
                "avg_time": avg([r.response_time for r in valid_results]),
            }
        }
        
        # Remove None categories
        summary = {k: v for k, v in summary.items() if v is not None}
        
        return summary


# ============================================================================
# RESPONSE QUALITY TESTING
# ============================================================================

class ResponseQualityTester:
    """Kelas untuk pengujian Response Quality"""
    
    def __init__(self, config_path: str, manual_mode: bool = False):
        self.config_path = config_path
        self.manual_mode = manual_mode
        self.query_chain = None
        self.results: List[ResponseQualityResult] = []
    
    def initialize(self):
        """Initialize QueryChain"""
        if MODULES_AVAILABLE:
            print("\n🔧 Initializing QueryChain...")
            self.query_chain = get_query_chain(self.config_path)
            print(f"   ✓ LLM Ready: {self.query_chain.llm is not None}")
        else:
            print("\n⚠️  Running in DEMO mode (modules not available)")
    
    def auto_score_quality(
        self,
        answer: str,
        sources: List,
        metadata: Dict
    ) -> Tuple[int, int, int]:
        """Auto-scoring kualitas respons."""
        relevance = 3
        accuracy = 3
        completeness = 3
        
        # === RELEVANCE ===
        avg_sim = metadata.get("avg_similarity", 0)
        if avg_sim >= 0.85:
            relevance = 5
        elif avg_sim >= 0.75:
            relevance = 4
        elif avg_sim >= 0.65:
            relevance = 3
        elif avg_sim >= 0.5:
            relevance = 2
        else:
            relevance = 1
        
        # === ACCURACY ===
        rel_check = metadata.get("relevance_check", "")
        if "PASSED" in rel_check.upper():
            accuracy = 4
            if len(sources) >= 2:
                accuracy = 5
        elif "FAILED" in rel_check.upper():
            accuracy = 2
        
        # Check for fallback
        answer_lower = answer.lower()
        fallback_phrases = ["tidak ditemukan", "maaf", "tidak ada informasi", "di luar cakupan"]
        if any(phrase in answer_lower for phrase in fallback_phrases):
            accuracy = max(1, accuracy - 2)
        
        # Bonus for specific numbers in answer (biaya)
        if any(char.isdigit() for char in answer):
            accuracy = min(5, accuracy + 1)
        
        # === COMPLETENESS ===
        answer_len = len(answer)
        num_sources = len(sources)
        
        if answer_len >= 500 and num_sources >= 2:
            completeness = 5
        elif answer_len >= 300 and num_sources >= 1:
            completeness = 4
        elif answer_len >= 150:
            completeness = 3
        elif answer_len >= 50:
            completeness = 2
        else:
            completeness = 1
        
        return relevance, accuracy, completeness
    
    def manual_score_quality(self, query: str, answer: str) -> Tuple[int, int, int]:
        """Manual scoring untuk response quality"""
        print(f"\n{'─'*70}")
        print(f"📝 PENILAIAN RESPONSE QUALITY")
        print(f"{'─'*70}")
        print(f"Query: {query}")
        print(f"\nJawaban:")
        preview = answer[:600] if len(answer) > 600 else answer
        print(f"  {preview}...")
        print(f"\n{'─'*70}")
        print("Skala Penilaian (1-5):")
        print("  5 = Sangat Baik (jawaban lengkap, spesifik, ada angka)")
        print("  4 = Baik (jawaban informatif, cukup detail)")
        print("  3 = Cukup (jawaban ada tapi kurang detail)")
        print("  2 = Kurang (jawaban tidak jelas/tidak spesifik)")
        print("  1 = Sangat Kurang (tidak menjawab)")
        print(f"{'─'*70}")
        
        def get_score(dimension: str) -> int:
            while True:
                try:
                    score = int(input(f"{dimension} (1-5): ").strip())
                    if 1 <= score <= 5:
                        return score
                    print("❌ Masukkan angka 1-5!")
                except ValueError:
                    print("❌ Input tidak valid!")
                except KeyboardInterrupt:
                    print("\n⚠️  Using default score 3")
                    return 3
        
        relevance = get_score("Relevance")
        accuracy = get_score("Accuracy")
        completeness = get_score("Completeness")
        
        return relevance, accuracy, completeness
    
    def evaluate_query(self, query_data: Dict) -> ResponseQualityResult:
        """Evaluasi response quality untuk satu query"""
        query_id = query_data["id"]
        query = query_data["query"]
        category = query_data["category"]
        
        result = ResponseQualityResult(
            query_id=query_id,
            query=query,
            category=category
        )
        
        try:
            start_time = time.time()
            
            if MODULES_AVAILABLE and self.query_chain:
                response = self.query_chain.query(
                    question=query,
                    filter=None,
                    verbose=False
                )
                answer = response.get("answer", "")
                sources = response.get("sources", [])
                metadata = response.get("metadata", {})
            else:
                # Demo mode
                answer = f"Simulasi jawaban untuk: {query}. Biaya pendidikan SD Al Azhar berkisar Rp 15.000.000 - Rp 25.000.000 per tahun, tergantung cabang dan program."
                sources = [{"doc": "simulated_1"}, {"doc": "simulated_2"}]
                metadata = {"avg_similarity": 0.78, "relevance_check": "PASSED"}
            
            result.response_time = time.time() - start_time
            result.answer = answer
            result.answer_length = len(answer)
            result.sources_count = len(sources)
            result.avg_similarity = metadata.get("avg_similarity", 0)
            
            # Score quality
            if self.manual_mode:
                rel, acc, comp = self.manual_score_quality(query, answer)
            else:
                rel, acc, comp = self.auto_score_quality(answer, sources, metadata)
            
            result.relevance = rel
            result.accuracy = acc
            result.completeness = comp
            result.average = (rel + acc + comp) / 3
            
        except Exception as e:
            result.error = str(e)
            print(f"   ❌ Error: {e}")
        
        return result
    
    def run_all_tests(self, sample_size: int = 10) -> List[ResponseQualityResult]:
        """Jalankan pengujian response quality (sample)"""
        print("\n" + "="*70)
        print("📝 PENGUJIAN RESPONSE QUALITY")
        print("="*70)
        print(f"Sample Size: {sample_size} queries from each category")
        
        self.initialize()
        
        # Sample queries dari setiap kategori
        samples = []
        samples.extend(QUERY_BIAYA_SEKOLAH[:4])      # 4 dari biaya sekolah
        samples.extend(QUERY_BIAYA_FORMULIR[:2])     # 2 dari formulir
        samples.extend(QUERY_SYARAT[:1])              # 1 dari syarat
        samples.extend(QUERY_UANG_PANGKAL[:3])       # 3 dari uang pangkal
        
        for i, q_data in enumerate(samples, 1):
            print(f"\n[{i}/{len(samples)}] {q_data['id']}: {q_data['query'][:60]}...")
            result = self.evaluate_query(q_data)
            self.results.append(result)
            
            if result.error:
                print(f"   ❌ Error: {result.error}")
            else:
                print(f"   ✓ R={result.relevance}, A={result.accuracy}, C={result.completeness}, "
                      f"Avg={result.average:.2f}, Time={result.response_time:.3f}s")
        
        return self.results
    
    def get_summary(self) -> Dict:
        """Hitung ringkasan"""
        valid_results = [r for r in self.results if not r.error]
        
        if not valid_results:
            return {
                "count": 0,
                "avg_relevance": 0,
                "avg_accuracy": 0,
                "avg_completeness": 0,
                "avg_overall": 0,
                "avg_response_time": 0
            }
        
        return {
            "count": len(valid_results),
            "avg_relevance": sum(r.relevance for r in valid_results) / len(valid_results),
            "avg_accuracy": sum(r.accuracy for r in valid_results) / len(valid_results),
            "avg_completeness": sum(r.completeness for r in valid_results) / len(valid_results),
            "avg_overall": sum(r.average for r in valid_results) / len(valid_results),
            "avg_response_time": sum(r.response_time for r in valid_results) / len(valid_results),
        }


# ============================================================================
# REPORT GENERATION
# ============================================================================

class ReportGenerator:
    """Generator laporan hasil pengujian"""
    
    def __init__(self, output_dir: str = Config.OUTPUT_DIR):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def generate_markdown_report(
        self,
        retrieval_results: List[RetrievalResult],
        retrieval_summary: Dict,
        response_results: List[ResponseQualityResult],
        response_summary: Dict,
        filename: str = "rag_performance_report_biaya.md"
    ) -> str:
        """Generate laporan Markdown"""
        
        filepath = os.path.join(self.output_dir, filename)
        lines = []
        
        # Header
        lines.append("# Pengujian Performa RAG - Query Biaya Sekolah\n")
        lines.append(f"**Tanggal Pengujian:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        lines.append("**Fokus:** Query Informational tentang Biaya Sekolah Al Azhar\n")
        lines.append("---\n")
        
        # Executive Summary
        lines.append("\n## Executive Summary\n")
        total_stats = retrieval_summary.get("total", {})
        lines.append(f"- **Total Query:** {total_stats.get('count', 0)} (Informational Only)\n")
        lines.append(f"- **Precision@3:** {total_stats.get('precision_at_3', 0):.1%}\n")
        lines.append(f"- **Recall@3:** {total_stats.get('recall_at_3', 0):.1%}\n")
        lines.append(f"- **Avg Response Time:** {total_stats.get('avg_time', 0):.3f}s\n")
        lines.append(f"- **Response Quality:** {response_summary.get('avg_overall', 0):.2f}/5.00\n")
        
        # =====================================================================
        # RETRIEVAL ACCURACY
        # =====================================================================
        lines.append("\n## Pengujian Retrieval Accuracy\n")
        
        # By Category
        lines.append("\n### Hasil Per Kategori Query\n")
        
        category_names = {
            "biaya_sekolah": "A. Query Biaya Sekolah",
            "biaya_formulir": "B. Query Biaya Formulir/Pendaftaran",
            "syarat_pendaftaran": "C. Query Syarat Pendaftaran",
            "uang_pangkal": "D. Query Uang Pangkal"
        }
        
        for cat_key, cat_name in category_names.items():
            cat_stats = retrieval_summary.get(cat_key)
            if not cat_stats:
                continue
            
            lines.append(f"\n#### {cat_name}\n")
            lines.append(f"- Jumlah Query: {cat_stats.get('count', 0)}\n")
            lines.append(f"- Precision@3: {cat_stats.get('precision_at_3', 0):.1%}\n")
            lines.append(f"- Recall@3: {cat_stats.get('recall_at_3', 0):.1%}\n")
            lines.append(f"- Avg Response Time: {cat_stats.get('avg_time', 0):.3f}s\n")
        
        # Detailed Table
        lines.append("\n### Tabel Hasil Detail - Retrieval\n")
        lines.append("| No | ID | Query | Cat | P@1 | P@3 | P@5 | R@3 | SR | CR | TR | Time |")
        lines.append("|:--:|:--:|-------|:---:|:---:|:---:|:---:|:---:|:--:|:--:|:--:|:----:|")
        
        for i, r in enumerate(retrieval_results, 1):
            if r.error:
                lines.append(f"| {i} | {r.query_id} | Error | - | - | - | - | - | - | - | - | - |")
            else:
                query_short = r.query[:40] + "..." if len(r.query) > 40 else r.query
                cat_short = r.category[:5]
                lines.append(
                    f"| {i} | {r.query_id} | {query_short} | {cat_short} | "
                    f"{r.precision_at_1:.0%} | {r.precision_at_3:.0%} | {r.precision_at_5:.0%} | "
                    f"{r.recall_at_3:.0%} | {r.sangat_relevan_count} | {r.cukup_relevan_count} | "
                    f"{r.tidak_relevan_count} | {r.response_time:.3f} |"
                )
        
        # Summary row
        lines.append(f"| | **AVG** | - | - | "
                    f"**{total_stats.get('precision_at_1', 0):.0%}** | "
                    f"**{total_stats.get('precision_at_3', 0):.0%}** | "
                    f"**{total_stats.get('precision_at_5', 0):.0%}** | "
                    f"**{total_stats.get('recall_at_3', 0):.0%}** | - | - | - | "
                    f"**{total_stats.get('avg_time', 0):.3f}** |")
        
        # Keterangan
        lines.append("\n**Keterangan:** SR=Sangat Relevan, CR=Cukup Relevan, TR=Tidak Relevan\n")
        
        # =====================================================================
        # RESPONSE QUALITY
        # =====================================================================
        if response_results:
            lines.append("\n## Pengujian Response Quality\n")
            lines.append(f"Sample: {len(response_results)} queries\n")
            
            lines.append("\n### Tabel Hasil Response Quality\n")
            lines.append("| No | ID | Query | R | A | C | Avg | Len | Src | Sim | Time |")
            lines.append("|:--:|:--:|-------|:-:|:-:|:-:|:---:|:---:|:---:|:---:|:----:|")
            
            for i, r in enumerate(response_results, 1):
                if r.error:
                    lines.append(f"| {i} | {r.query_id} | Error | - | - | - | - | - | - | - | - |")
                else:
                    query_short = r.query[:30] + "..." if len(r.query) > 30 else r.query
                    lines.append(
                        f"| {i} | {r.query_id} | {query_short} | "
                        f"{r.relevance} | {r.accuracy} | {r.completeness} | {r.average:.2f} | "
                        f"{r.answer_length} | {r.sources_count} | {r.avg_similarity:.2f} | "
                        f"{r.response_time:.3f} |"
                    )
            
            # Summary
            lines.append(f"| | **AVG** | - | "
                        f"**{response_summary.get('avg_relevance', 0):.2f}** | "
                        f"**{response_summary.get('avg_accuracy', 0):.2f}** | "
                        f"**{response_summary.get('avg_completeness', 0):.2f}** | "
                        f"**{response_summary.get('avg_overall', 0):.2f}** | - | - | - | "
                        f"**{response_summary.get('avg_response_time', 0):.3f}** |")
            
            lines.append("\n**Keterangan:** R=Relevance, A=Accuracy, C=Completeness, Len=Answer Length, Src=Sources, Sim=Similarity\n")
        
        # =====================================================================
        # KESIMPULAN
        # =====================================================================
        lines.append("\n## Kesimpulan\n")
        lines.append(f"1. **Retrieval Performance:**\n")
        lines.append(f"   - Precision@3: {total_stats.get('precision_at_3', 0):.1%}\n")
        lines.append(f"   - Recall@3: {total_stats.get('recall_at_3', 0):.1%}\n")
        lines.append(f"   - Avg Response Time: {total_stats.get('avg_time', 0):.3f}s\n")
        
        if response_summary.get('count', 0) > 0:
            lines.append(f"\n2. **Response Quality:**\n")
            lines.append(f"   - Relevance: {response_summary.get('avg_relevance', 0):.2f}/5\n")
            lines.append(f"   - Accuracy: {response_summary.get('avg_accuracy', 0):.2f}/5\n")
            lines.append(f"   - Completeness: {response_summary.get('avg_completeness', 0):.2f}/5\n")
            lines.append(f"   - Overall: {response_summary.get('avg_overall', 0):.2f}/5\n")
        
        lines.append(f"\n3. **Rekomendasi:** Berdasarkan hasil pengujian, sistem RAG menunjukkan performa "
                    f"{'baik' if total_stats.get('precision_at_3', 0) >= 0.7 else 'perlu ditingkatkan'} "
                    f"untuk query informational tentang biaya sekolah.\n")
        
        # Write file
        content = "\n".join(lines)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"\n✅ Markdown report saved: {filepath}")
        return filepath
    
    def generate_csv_reports(
        self,
        retrieval_results: List[RetrievalResult],
        response_results: List[ResponseQualityResult]
    ):
        """Generate CSV reports"""
        
        # Retrieval CSV
        ret_path = os.path.join(self.output_dir, "retrieval_results_biaya.csv")
        with open(ret_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Query ID", "Query", "Category", "Subcategory", "Jenjang", "Cabang",
                "P@1", "P@3", "P@5", "R@1", "R@3", "R@5",
                "Sangat Relevan", "Cukup Relevan", "Tidak Relevan",
                "Time (s)", "Error"
            ])
            for r in retrieval_results:
                writer.writerow([
                    r.query_id, r.query, r.category, r.subcategory, r.jenjang, r.cabang,
                    f"{r.precision_at_1:.4f}", f"{r.precision_at_3:.4f}", f"{r.precision_at_5:.4f}",
                    f"{r.recall_at_1:.4f}", f"{r.recall_at_3:.4f}", f"{r.recall_at_5:.4f}",
                    r.sangat_relevan_count, r.cukup_relevan_count, r.tidak_relevan_count,
                    f"{r.response_time:.4f}", r.error or ""
                ])
        print(f"✅ Retrieval CSV saved: {ret_path}")
        
        # Response Quality CSV
        if response_results:
            res_path = os.path.join(self.output_dir, "response_quality_results_biaya.csv")
            with open(res_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Query ID", "Query", "Category",
                    "Relevance", "Accuracy", "Completeness", "Average",
                    "Answer Length", "Sources", "Similarity", "Time (s)", "Error"
                ])
                for r in response_results:
                    writer.writerow([
                        r.query_id, r.query, r.category,
                        r.relevance, r.accuracy, r.completeness, f"{r.average:.4f}",
                        r.answer_length, r.sources_count, f"{r.avg_similarity:.4f}",
                        f"{r.response_time:.4f}", r.error or ""
                    ])
            print(f"✅ Response Quality CSV saved: {res_path}")
    
    def generate_judgement_sheet(
        self,
        retrieval_results: List[RetrievalResult],
        filename: str = "judgement_sheet_biaya.csv"
    ):
        """Generate judgement sheet for manual verification"""
        
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Query ID", "Query", "Category", "Jenjang", "Cabang",
                "Chunk-1", "Chunk-2", "Chunk-3", "Chunk-4", "Chunk-5",
                "P@3", "R@3"
            ])
            
            for r in retrieval_results:
                scores = [c.relevance_score for c in r.chunks[:5]]
                scores_padded = scores + [""] * (5 - len(scores))
                
                writer.writerow([
                    r.query_id, r.query[:70], r.category, r.jenjang, r.cabang,
                    *scores_padded,
                    f"{r.precision_at_3:.2%}", f"{r.recall_at_3:.2%}"
                ])
        
        print(f"✅ Judgement sheet saved: {filepath}")
        return filepath


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="RAG Performance Testing - Fokus Query Biaya Sekolah",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python rag_performance_test_biaya.py --config config.yaml
  python rag_performance_test_biaya.py --config config.yaml --retrieval-only
  python rag_performance_test_biaya.py --config config.yaml --manual
        """
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=Config.DEFAULT_CONFIG_PATH,
        help="Path to config.yaml"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=Config.OUTPUT_DIR,
        help="Output directory"
    )
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Only run retrieval accuracy tests"
    )
    parser.add_argument(
        "--response-only",
        action="store_true",
        help="Only run response quality tests"
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Enable manual scoring mode"
    )
    parser.add_argument(
        "--response-sample",
        type=int,
        default=10,
        help="Number of queries for response quality testing (default: 10)"
    )
    parser.add_argument(
        "--scoring-mode",
        type=str,
        choices=["lenient", "moderate", "strict"],
        default="strict",
        help="Scoring strictness: lenient (easy 100%%), moderate (balanced), strict (realistic)"
    )
    
    args = parser.parse_args()
    Config.OUTPUT_DIR = args.output
    Config.SCORING_MODE = args.scoring_mode
    
    print("\n" + "="*70)
    print("🧪 RAG PERFORMANCE TESTING - QUERY BIAYA SEKOLAH")
    print("   Fokus: Informational Queries Only (40 queries)")
    print("="*70)
    print(f"📁 Config: {args.config}")
    print(f"📂 Output: {args.output}")
    print(f"🔧 Manual Mode: {args.manual}")
    print(f"⚙️  Scoring Mode: {args.scoring_mode.upper()}")
    print(f"📊 Modules Available: {MODULES_AVAILABLE}")
    print(f"📝 Response Sample Size: {args.response_sample}")
    
    retrieval_results = []
    retrieval_summary = {}
    response_results = []
    response_summary = {}
    
    try:
        # Run Retrieval Tests
        if not args.response_only:
            retrieval_tester = RetrievalTester(args.config, manual_mode=args.manual)
            retrieval_results = retrieval_tester.run_all_tests()
            retrieval_summary = retrieval_tester.get_summary()
        
        # Run Response Quality Tests
        if not args.retrieval_only:
            response_tester = ResponseQualityTester(args.config, manual_mode=args.manual)
            response_results = response_tester.run_all_tests(sample_size=args.response_sample)
            response_summary = response_tester.get_summary()
        
        # Generate Reports
        print("\n" + "="*70)
        print("📄 GENERATING REPORTS")
        print("="*70)
        
        report_gen = ReportGenerator(args.output)
        
        report_gen.generate_markdown_report(
            retrieval_results, retrieval_summary,
            response_results, response_summary
        )
        
        report_gen.generate_csv_reports(retrieval_results, response_results)
        
        if retrieval_results:
            report_gen.generate_judgement_sheet(retrieval_results)
        
        # Print Summary
        print("\n" + "="*70)
        print("📊 RINGKASAN HASIL")
        print("="*70)
        
        if retrieval_summary:
            total = retrieval_summary.get("total", {})
            
            print(f"\n🔵 Retrieval Accuracy:")
            print(f"   ├─ Total Queries: {total.get('count', 0)}")
            print(f"   ├─ Precision@1: {total.get('precision_at_1', 0):.1%}")
            print(f"   ├─ Precision@3: {total.get('precision_at_3', 0):.1%}")
            print(f"   ├─ Precision@5: {total.get('precision_at_5', 0):.1%}")
            print(f"   ├─ Recall@3: {total.get('recall_at_3', 0):.1%}")
            print(f"   └─ Avg Time: {total.get('avg_time', 0):.3f}s")
            
            # By category
            print(f"\n   📁 By Category:")
            for cat_key in ["biaya_sekolah", "biaya_formulir", "syarat_pendaftaran", "uang_pangkal"]:
                cat_stats = retrieval_summary.get(cat_key)
                if cat_stats:
                    cat_name = cat_key.replace("_", " ").title()
                    print(f"      • {cat_name}: P@3={cat_stats.get('precision_at_3', 0):.1%}, "
                          f"R@3={cat_stats.get('recall_at_3', 0):.1%} (n={cat_stats.get('count', 0)})")
        
        if response_summary and response_summary.get('count', 0) > 0:
            print(f"\n📝 Response Quality:")
            print(f"   ├─ Queries Tested: {response_summary.get('count', 0)}")
            print(f"   ├─ Avg Relevance: {response_summary.get('avg_relevance', 0):.2f}/5")
            print(f"   ├─ Avg Accuracy: {response_summary.get('avg_accuracy', 0):.2f}/5")
            print(f"   ├─ Avg Completeness: {response_summary.get('avg_completeness', 0):.2f}/5")
            print(f"   ├─ Overall Average: {response_summary.get('avg_overall', 0):.2f}/5")
            print(f"   └─ Avg Time: {response_summary.get('avg_response_time', 0):.3f}s")
        
        print(f"\n📂 Output Directory: {args.output}/")
        print(f"   ├─ rag_performance_report_biaya.md")
        print(f"   ├─ retrieval_results_biaya.csv")
        print(f"   ├─ response_quality_results_biaya.csv")
        print(f"   └─ judgement_sheet_biaya.csv")
        print("\n✅ Testing completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Testing interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()