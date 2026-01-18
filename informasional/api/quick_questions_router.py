# ============================================================================
# FILE: informasional/routers/quick_questions_router.py
# Quick Questions API - Generate relevant questions based on knowledge base
# ============================================================================
"""
Quick Questions Router - Generate pertanyaan relevan

ENDPOINTS:
- GET  /questions/suggested          : Get suggested questions
- GET  /questions/by-document/{id}   : Get questions for specific document
- GET  /questions/by-jenjang/{jenjang}: Get questions for jenjang
- GET  /questions/popular            : Get popular/common questions
- POST /questions/generate           : Generate questions from content
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from collections import defaultdict
import random

from informasional.utils.vectorstore_utils import get_vectorstore
from informasional.core.config_loader import get_config
from transaksional.app.config import settings


# ============================================================================
# ROUTER SETUP
# ============================================================================
router = APIRouter(
    prefix=f"{settings.informational_prefix}/questions",
    tags=["Quick Questions"]
)

CONFIG_PATH = "informasional/config/config.yaml"


# ============================================================================
# SCHEMAS
# ============================================================================
class QuestionItem(BaseModel):
    """Single question item"""
    question: str
    category: str
    jenjang: Optional[str] = None
    document_id: Optional[str] = None
    relevance: Optional[float] = None


class GenerateQuestionsRequest(BaseModel):
    """Request untuk generate questions"""
    content: str = Field(..., min_length=10)
    num_questions: int = Field(default=5, ge=1, le=10)


# ============================================================================
# PREDEFINED QUESTION TEMPLATES
# ============================================================================
QUESTION_TEMPLATES = {
    "biaya": [
        "Berapa biaya pendaftaran {jenjang} Al-Azhar {cabang}?",
        "Berapa SPP bulanan {jenjang} Al-Azhar?",
        "Apa saja komponen biaya pendidikan {jenjang}?",
        "Apakah ada biaya uang pangkal untuk {jenjang}?",
        "Berapa total biaya masuk {jenjang} Al-Azhar tahun {tahun}?",
    ],
    "pendaftaran": [
        "Bagaimana cara mendaftar di {jenjang} Al-Azhar?",
        "Apa saja persyaratan pendaftaran {jenjang}?",
        "Kapan jadwal pendaftaran {jenjang} Al-Azhar?",
        "Dokumen apa saja yang diperlukan untuk daftar {jenjang}?",
        "Apakah ada tes masuk untuk {jenjang} Al-Azhar?",
    ],
    "program": [
        "Apa saja program unggulan {jenjang} Al-Azhar?",
        "Kurikulum apa yang digunakan di {jenjang} Al-Azhar?",
        "Apakah ada program tahfidz di {jenjang}?",
        "Apa saja kegiatan ekstrakurikuler di {jenjang}?",
        "Bagaimana sistem pembelajaran di {jenjang} Al-Azhar?",
    ],
    "fasilitas": [
        "Apa saja fasilitas yang tersedia di {jenjang} Al-Azhar {cabang}?",
        "Apakah ada fasilitas antar jemput?",
        "Bagaimana fasilitas perpustakaan di {jenjang}?",
        "Apakah ada kantin di sekolah?",
    ],
    "umum": [
        "Dimana lokasi {jenjang} Al-Azhar {cabang}?",
        "Jam berapa sekolah dimulai dan selesai?",
        "Berapa jumlah siswa per kelas di {jenjang}?",
        "Siapa kepala sekolah {jenjang} Al-Azhar {cabang}?",
        "Bagaimana cara menghubungi {jenjang} Al-Azhar?",
    ],
    "sk": [
        "Kapan {jenjang} Al-Azhar {cabang} didirikan?",
        "Apa nomor SK pendirian {jenjang} Al-Azhar {cabang}?",
        "Siapa pendiri {jenjang} Al-Azhar?",
    ]
}

# Common questions (tidak perlu context)
COMMON_QUESTIONS = [
    {
        "question": "Apa saja jenjang pendidikan yang tersedia di Al-Azhar?",
        "category": "umum"
    },
    {
        "question": "Berapa biaya pendidikan di Al-Azhar?",
        "category": "biaya"
    },
    {
        "question": "Bagaimana cara mendaftar di Al-Azhar?",
        "category": "pendaftaran"
    },
    {
        "question": "Apa keunggulan sekolah Al-Azhar?",
        "category": "program"
    },
    {
        "question": "Dimana saja lokasi sekolah Al-Azhar?",
        "category": "umum"
    },
    {
        "question": "Kapan pendaftaran siswa baru dibuka?",
        "category": "pendaftaran"
    },
    {
        "question": "Apakah Al-Azhar menerima siswa pindahan?",
        "category": "pendaftaran"
    },
    {
        "question": "Apa saja program keagamaan di Al-Azhar?",
        "category": "program"
    },
]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
def get_documents_metadata() -> List[Dict]:
    """Get all documents metadata from vectorstore"""
    vectorstore_manager = get_vectorstore(CONFIG_PATH)
    collection = vectorstore_manager.collection
    
    try:
        results = collection.get(include=["metadatas"])
    except:
        return []
    
    if not results['ids']:
        return []
    
    # Group by document_id
    docs = {}
    for metadata in results['metadatas']:
        doc_id = metadata.get('document_id', 'unknown')
        if doc_id not in docs:
            docs[doc_id] = metadata
    
    return list(docs.values())


def generate_questions_from_metadata(
    metadata: Dict,
    num_questions: int = 3
) -> List[Dict]:
    """Generate questions based on document metadata"""
    questions = []
    
    jenjang = metadata.get('jenjang', '')
    cabang = metadata.get('cabang', '')
    tahun = metadata.get('tahun', '')
    category = metadata.get('category', metadata.get('kategori', '')).lower()
    source = metadata.get('source', '')
    
    # Determine question category based on document
    if 'biaya' in source.lower() or 'spp' in source.lower():
        templates = QUESTION_TEMPLATES.get('biaya', [])
    elif 'ppdb' in source.lower() or 'pendaftaran' in source.lower():
        templates = QUESTION_TEMPLATES.get('pendaftaran', [])
    elif 'sk' in source.lower():
        templates = QUESTION_TEMPLATES.get('sk', [])
    elif 'program' in source.lower() or 'kurikulum' in source.lower():
        templates = QUESTION_TEMPLATES.get('program', [])
    else:
        templates = QUESTION_TEMPLATES.get('umum', [])
    
    # Generate questions from templates
    for template in templates[:num_questions]:
        question = template.format(
            jenjang=jenjang or "sekolah",
            cabang=cabang or "",
            tahun=tahun or "ini"
        )
        # Clean up extra spaces
        question = ' '.join(question.split())
        
        questions.append({
            "question": question,
            "category": category or "umum",
            "jenjang": jenjang,
            "document_id": metadata.get('document_id')
        })
    
    return questions


# ============================================================================
# API: Get Suggested Questions
# ============================================================================
@router.get("/suggested")
async def get_suggested_questions(
    jenjang: Optional[str] = Query(default=None, description="Filter by jenjang"),
    cabang: Optional[str] = Query(default=None, description="Filter by cabang"),
    category: Optional[str] = Query(default=None, description="Filter by category: biaya, pendaftaran, program, umum"),
    limit: int = Query(default=10, ge=1, le=50)
):
    """
    Get suggested questions based on knowledge base content
    
    Questions are generated from:
    1. Document metadata in vectorstore
    2. Predefined question templates
    3. Common questions
    
    Returns questions relevant to available documents
    """
    # Get documents metadata
    docs_metadata = get_documents_metadata()
    
    all_questions = []
    
    # Generate questions from each document
    for meta in docs_metadata:
        # Apply filters
        if jenjang and meta.get('jenjang', '').lower() != jenjang.lower():
            continue
        if cabang and cabang.lower() not in meta.get('cabang', '').lower():
            continue
        
        questions = generate_questions_from_metadata(meta, num_questions=2)
        
        # Apply category filter
        if category:
            questions = [q for q in questions if category.lower() in q.get('category', '').lower()]
        
        all_questions.extend(questions)
    
    # Add common questions
    common = COMMON_QUESTIONS.copy()
    if category:
        common = [q for q in common if category.lower() in q.get('category', '').lower()]
    
    all_questions.extend(common)
    
    # Deduplicate by question text
    seen = set()
    unique_questions = []
    for q in all_questions:
        if q['question'] not in seen:
            seen.add(q['question'])
            unique_questions.append(q)
    
    # Shuffle and limit
    random.shuffle(unique_questions)
    unique_questions = unique_questions[:limit]
    
    return {
        "total": len(unique_questions),
        "filters": {
            "jenjang": jenjang,
            "cabang": cabang,
            "category": category
        },
        "questions": unique_questions
    }


# ============================================================================
# API: Get Questions for Specific Document
# ============================================================================
@router.get("/by-document/{document_id}")
async def get_questions_by_document(
    document_id: str,
    limit: int = Query(default=5, ge=1, le=20)
):
    """
    Get relevant questions for specific document
    """
    vectorstore_manager = get_vectorstore(CONFIG_PATH)
    
    # Get document chunks
    chunks = vectorstore_manager.get_by_document_id(document_id)
    
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {document_id}"
        )
    
    # Get metadata from first chunk
    metadata = chunks[0]['metadata']
    
    # Generate questions
    questions = generate_questions_from_metadata(metadata, num_questions=limit)
    
    # Add some generic questions
    jenjang = metadata.get('jenjang', 'sekolah')
    generic = [
        f"Informasi lengkap tentang {metadata.get('source', 'dokumen ini')}",
        f"Apa isi utama dari dokumen {metadata.get('source', 'ini')}?",
    ]
    
    for g in generic[:2]:
        questions.append({
            "question": g,
            "category": "umum",
            "jenjang": jenjang,
            "document_id": document_id
        })
    
    return {
        "document_id": document_id,
        "source": metadata.get('source', 'Unknown'),
        "total": len(questions),
        "questions": questions[:limit]
    }


# ============================================================================
# API: Get Questions by Jenjang
# ============================================================================
@router.get("/by-jenjang/{jenjang}")
async def get_questions_by_jenjang(
    jenjang: str,
    limit: int = Query(default=10, ge=1, le=30)
):
    """
    Get relevant questions for specific jenjang (TK, SD, SMP, SMA)
    """
    jenjang_upper = jenjang.upper()
    
    # Validate jenjang
    valid_jenjang = ['TK', 'SD', 'SMP', 'SMA', 'SMK']
    if jenjang_upper not in valid_jenjang:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid jenjang. Must be one of: {valid_jenjang}"
        )
    
    questions = []
    
    # Generate from all categories
    for category, templates in QUESTION_TEMPLATES.items():
        for template in templates[:2]:
            question = template.format(
                jenjang=jenjang_upper,
                cabang="",
                tahun="ini"
            )
            question = ' '.join(question.split())
            
            questions.append({
                "question": question,
                "category": category,
                "jenjang": jenjang_upper
            })
    
    # Shuffle and limit
    random.shuffle(questions)
    questions = questions[:limit]
    
    return {
        "jenjang": jenjang_upper,
        "total": len(questions),
        "questions": questions
    }


# ============================================================================
# API: Get Popular/Common Questions
# ============================================================================
@router.get("/popular")
async def get_popular_questions(
    limit: int = Query(default=10, ge=1, le=20)
):
    """
    Get popular/common questions
    
    These are frequently asked questions that don't require specific context
    """
    questions = COMMON_QUESTIONS.copy()
    
    # Add some dynamic questions based on available data
    docs_metadata = get_documents_metadata()
    
    # Get unique jenjang
    jenjang_set = set()
    for meta in docs_metadata:
        if meta.get('jenjang'):
            jenjang_set.add(meta['jenjang'])
    
    # Add jenjang-specific popular questions
    for jenjang in list(jenjang_set)[:3]:
        questions.append({
            "question": f"Berapa biaya pendidikan {jenjang} Al-Azhar?",
            "category": "biaya",
            "jenjang": jenjang
        })
        questions.append({
            "question": f"Bagaimana cara mendaftar di {jenjang} Al-Azhar?",
            "category": "pendaftaran",
            "jenjang": jenjang
        })
    
    # Deduplicate
    seen = set()
    unique = []
    for q in questions:
        if q['question'] not in seen:
            seen.add(q['question'])
            unique.append(q)
    
    return {
        "total": min(len(unique), limit),
        "questions": unique[:limit]
    }


# ============================================================================
# API: Get Questions by Category
# ============================================================================
@router.get("/by-category/{category}")
async def get_questions_by_category(
    category: str,
    jenjang: Optional[str] = None,
    limit: int = Query(default=10, ge=1, le=30)
):
    """
    Get questions by category
    
    Categories: biaya, pendaftaran, program, fasilitas, umum, sk
    """
    category_lower = category.lower()
    
    # Validate category
    valid_categories = list(QUESTION_TEMPLATES.keys())
    if category_lower not in valid_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be one of: {valid_categories}"
        )
    
    templates = QUESTION_TEMPLATES.get(category_lower, [])
    questions = []
    
    # Get available jenjang from vectorstore
    docs_metadata = get_documents_metadata()
    jenjang_set = set()
    for meta in docs_metadata:
        if meta.get('jenjang'):
            jenjang_set.add(meta['jenjang'])
    
    # Filter jenjang if specified
    if jenjang:
        jenjang_set = {j for j in jenjang_set if j.lower() == jenjang.lower()}
    
    if not jenjang_set:
        jenjang_set = {'sekolah'}
    
    # Generate questions
    for j in jenjang_set:
        for template in templates:
            question = template.format(
                jenjang=j,
                cabang="",
                tahun="ini"
            )
            question = ' '.join(question.split())
            
            questions.append({
                "question": question,
                "category": category_lower,
                "jenjang": j
            })
    
    # Deduplicate and limit
    seen = set()
    unique = []
    for q in questions:
        if q['question'] not in seen:
            seen.add(q['question'])
            unique.append(q)
    
    random.shuffle(unique)
    
    return {
        "category": category_lower,
        "jenjang_filter": jenjang,
        "total": min(len(unique), limit),
        "questions": unique[:limit]
    }


# ============================================================================
# API: Get All Categories
# ============================================================================
@router.get("/categories")
async def get_question_categories():
    """
    Get available question categories
    """
    return {
        "categories": [
            {"id": "biaya", "name": "Biaya Pendidikan", "description": "Pertanyaan tentang biaya, SPP, uang pangkal"},
            {"id": "pendaftaran", "name": "Pendaftaran", "description": "Pertanyaan tentang PPDB, persyaratan, jadwal"},
            {"id": "program", "name": "Program & Kurikulum", "description": "Pertanyaan tentang program unggulan, kurikulum"},
            {"id": "fasilitas", "name": "Fasilitas", "description": "Pertanyaan tentang fasilitas sekolah"},
            {"id": "umum", "name": "Umum", "description": "Pertanyaan umum tentang sekolah"},
            {"id": "sk", "name": "SK & Legalitas", "description": "Pertanyaan tentang SK pendirian, legalitas"}
        ]
    }