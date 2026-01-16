# ============================================================================
# FILE: core/rag_factory.py
# ============================================================================
"""
RAG Factory - Singleton pattern untuk RAG components

Menggabungkan:
1. Enhanced Chunker
2. Smart Retriever dengan Document Aggregation
3. Query Chain

FLOW:
Document → Chunk (dengan document_id) → Embed → Store
Query → Retrieve → Aggregate by document_id → Build Context → LLM → Answer
"""

import os
from typing import Dict, Any, Optional
from dotenv import load_dotenv

from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings

# Local imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.enhanced_chunker import EnhancedChunker, DocumentProcessor
from utils.smart_retriever import SmartRetriever, EnhancedQueryChain

load_dotenv()

# ============================================================================
# DEFAULT CONFIG
# ============================================================================
DEFAULT_CONFIG = {
    "embeddings": {
        "model": "openai",
        "openai": {
            "model_name": "text-embedding-3-small",
            "dimensions": 1536
        },
        "huggingface": {
            "model_name": "sentence-transformers/all-MiniLM-L6-v2",
            "dimensions": 384,
            "device": "cpu"
        }
    },
    "chunking": {
        "strategy": "fixed_size",
        "fixed_size": {
            "chunk_size": 1000,
            "chunk_overlap": 200,
            "separators": ["\n\n", "\n", ".", " ", ""]
        }
    },
    "vectordb": {
        "chroma": {
            "collection_name": "alazhar_knowledge",
            "persist_directory": "./chroma_db",
            "distance_function": "cosine"
        }
    },
    "retrieval": {
        "top_k": 5,
        "similarity_threshold": 0.5,
        "max_documents": 3,
        "fetch_full_document": True
    },
    "llm": {
        "provider": "openai",
        "openai": {
            "model": "gpt-4o-mini",
            "temperature": 0.1,
            "max_tokens": 2000
        }
    }
}

# ============================================================================
# DEFAULT PROMPTS
# ============================================================================
DEFAULT_SYSTEM_PROMPT = """
ATURAN UTAMA - WAJIB DIPATUHI:
================================
1. Anda HARUS SELALU menjawab dalam BAHASA INDONESIA
2. JANGAN PERNAH menjawab dalam bahasa Inggris atau bahasa lain

IDENTITAS:
==========
Anda adalah asisten virtual resmi Yayasan Pesantren Islam Al-Azhar Jakarta.

TUGAS ANDA:
===========
- Memberikan informasi akurat tentang kebijakan, biaya, program, dan layanan YPI Al-Azhar
- Menjawab pertanyaan berdasarkan dokumen resmi yang diberikan
- WAJIB menyebutkan TAHUN/PERIODE dokumen jika tersedia
- Jika informasi tidak tersedia, katakan dengan jelas
"""

DEFAULT_QUERY_PROMPT = """
INSTRUKSI:
==========
1. Jawab HANYA dalam BAHASA INDONESIA
2. SEBUTKAN TAHUN/PERIODE dokumen jika ada
3. Jika konteks tidak relevan, katakan: "Maaf, saya tidak menemukan informasi tersebut."

Pertanyaan: {question}

Konteks dari dokumen resmi YPI Al-Azhar:
----------------------------------------
{context}
----------------------------------------

Jawaban (dalam Bahasa Indonesia):
"""


# ============================================================================
# SINGLETON COMPONENTS
# ============================================================================
_embeddings = None
_vectorstore = None
_chunker = None
_retriever = None
_query_chain = None
_config = None


def get_config(custom_config: Dict = None) -> Dict:
    """Get or set configuration"""
    global _config
    
    if custom_config:
        _config = {**DEFAULT_CONFIG, **custom_config}
    elif _config is None:
        _config = DEFAULT_CONFIG
    
    return _config


def get_embeddings(config: Dict = None) -> Any:
    """Get or create embeddings function"""
    global _embeddings
    
    if _embeddings is not None:
        return _embeddings
    
    cfg = get_config(config)
    embedding_cfg = cfg["embeddings"]
    
    if embedding_cfg["model"] == "openai":
        _embeddings = OpenAIEmbeddings(
            model=embedding_cfg["openai"]["model_name"],
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
        print(f"✅ Embeddings: OpenAI ({embedding_cfg['openai']['model_name']})")
    
    elif embedding_cfg["model"] == "huggingface":
        import torch
        device = embedding_cfg["huggingface"].get("device", "cpu")
        if device == "cuda" and not torch.cuda.is_available():
            device = "cpu"
        
        _embeddings = HuggingFaceEmbeddings(
            model_name=embedding_cfg["huggingface"]["model_name"],
            model_kwargs={"device": device},
            encode_kwargs={"normalize_embeddings": True}
        )
        print(f"✅ Embeddings: HuggingFace ({embedding_cfg['huggingface']['model_name']})")
    
    else:
        raise ValueError(f"Embedding tidak didukung: {embedding_cfg['model']}")
    
    return _embeddings


def get_vectorstore(config: Dict = None) -> Chroma:
    """Get or create vectorstore"""
    global _vectorstore
    
    if _vectorstore is not None:
        return _vectorstore
    
    cfg = get_config(config)
    chroma_cfg = cfg["vectordb"]["chroma"]
    
    _vectorstore = Chroma(
        collection_name=chroma_cfg["collection_name"],
        embedding_function=get_embeddings(cfg),
        persist_directory=chroma_cfg["persist_directory"],
        collection_metadata={"hnsw:space": chroma_cfg.get("distance_function", "cosine")}
    )
    
    print(f"✅ VectorStore: ChromaDB")
    print(f"   Collection: {chroma_cfg['collection_name']}")
    print(f"   Total chunks: {_vectorstore._collection.count()}")
    
    return _vectorstore


def get_chunker(config: Dict = None) -> EnhancedChunker:
    """Get or create chunker"""
    global _chunker
    
    if _chunker is not None:
        return _chunker
    
    cfg = get_config(config)
    _chunker = EnhancedChunker(config=cfg)
    
    chunk_cfg = cfg["chunking"]["fixed_size"]
    print(f"✅ Chunker: size={chunk_cfg['chunk_size']}, overlap={chunk_cfg['chunk_overlap']}")
    
    return _chunker


def get_retriever(config: Dict = None) -> SmartRetriever:
    """Get or create smart retriever"""
    global _retriever
    
    if _retriever is not None:
        return _retriever
    
    cfg = get_config(config)
    retrieval_cfg = cfg["retrieval"]
    
    _retriever = SmartRetriever(
        vectorstore=get_vectorstore(cfg),
        embedding_function=get_embeddings(cfg),
        top_k=retrieval_cfg["top_k"],
        similarity_threshold=retrieval_cfg.get("similarity_threshold", 0.5),
        max_documents=retrieval_cfg.get("max_documents", 3),
        fetch_full_document=retrieval_cfg.get("fetch_full_document", True)
    )
    
    print(f"✅ Retriever: Smart with Document Aggregation")
    print(f"   Top-K: {retrieval_cfg['top_k']}")
    print(f"   Max documents: {retrieval_cfg.get('max_documents', 3)}")
    print(f"   Fetch full document: {retrieval_cfg.get('fetch_full_document', True)}")
    
    return _retriever


def build_llm(config: Dict = None):
    """Build LLM"""
    cfg = get_config(config)
    llm_cfg = cfg["llm"]
    provider = llm_cfg["provider"]
    
    if provider == "openai":
        llm = ChatOpenAI(
            model=llm_cfg["openai"]["model"],
            temperature=llm_cfg["openai"]["temperature"],
            max_tokens=llm_cfg["openai"]["max_tokens"]
        )
        print(f"✅ LLM: OpenAI ({llm_cfg['openai']['model']})")
        return llm
    
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model=llm_cfg["gemini"]["model"],
            temperature=llm_cfg["gemini"]["temperature"],
            max_output_tokens=llm_cfg["gemini"]["max_tokens"]
        )
        print(f"✅ LLM: Gemini ({llm_cfg['gemini']['model']})")
        return llm
    
    else:
        raise ValueError(f"LLM provider tidak didukung: {provider}")


def get_query_chain(
    config: Dict = None,
    system_prompt: str = None,
    query_prompt: str = None
) -> EnhancedQueryChain:
    """
    Get or create query chain (SINGLETON)
    
    Args:
        config: Custom config (optional)
        system_prompt: Custom system prompt (optional)
        query_prompt: Custom query prompt (optional)
    
    Returns:
        EnhancedQueryChain instance
    """
    global _query_chain
    
    if _query_chain is not None:
        return _query_chain
    
    print("\n" + "="*60)
    print("🔄 INITIALIZING RAG PIPELINE")
    print("="*60)
    
    cfg = get_config(config)
    
    _query_chain = EnhancedQueryChain(
        smart_retriever=get_retriever(cfg),
        llm=build_llm(cfg),
        system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT,
        query_prompt=query_prompt or DEFAULT_QUERY_PROMPT
    )
    
    print("="*60)
    print("✅ RAG PIPELINE READY")
    print("="*60 + "\n")
    
    return _query_chain


def get_document_processor(config: Dict = None) -> DocumentProcessor:
    """Get document processor for ingestion"""
    return DocumentProcessor(chunker=get_chunker(config))


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================
def reset_singletons():
    """Reset all singletons (useful for testing)"""
    global _embeddings, _vectorstore, _chunker, _retriever, _query_chain, _config
    _embeddings = None
    _vectorstore = None
    _chunker = None
    _retriever = None
    _query_chain = None
    _config = None
    print("🔄 All singletons reset")


def inspect_vectorstore() -> Dict[str, Any]:
    """Inspect current vectorstore state"""
    vs = get_vectorstore()
    collection = vs._collection
    
    count = collection.count()
    
    if count == 0:
        return {
            "total_chunks": 0,
            "unique_documents": 0,
            "message": "VectorStore is empty"
        }
    
    # Get all metadata
    all_data = collection.get(include=['metadatas'])
    
    # Analyze
    doc_ids = set()
    sources = set()
    jenjang_dist = {}
    
    for meta in all_data.get('metadatas', []):
        if meta:
            doc_id = meta.get('document_id')
            if doc_id:
                doc_ids.add(doc_id)
            
            source = meta.get('source')
            if source:
                sources.add(source)
            
            jenjang = meta.get('jenjang', 'Unknown')
            jenjang_dist[jenjang] = jenjang_dist.get(jenjang, 0) + 1
    
    return {
        "total_chunks": count,
        "unique_documents": len(doc_ids),
        "unique_sources": len(sources),
        "document_ids": list(doc_ids)[:20],
        "sources": list(sources)[:20],
        "jenjang_distribution": jenjang_dist,
        "sample_metadata": all_data.get('metadatas', [])[:3]
    }


# ============================================================================
# TEST
# ============================================================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print("RAG FACTORY TEST")
    print("="*60)
    
    # Initialize all components
    chain = get_query_chain()
    
    # Inspect vectorstore
    print("\n📊 VectorStore Status:")
    info = inspect_vectorstore()
    for key, value in info.items():
        if isinstance(value, dict):
            print(f"   {key}:")
            for k, v in value.items():
                print(f"      {k}: {v}")
        elif isinstance(value, list):
            print(f"   {key}: {value[:5]}{'...' if len(value) > 5 else ''}")
        else:
            print(f"   {key}: {value}")
