# ============================================================================
# FILE: informasional/core/rag_factory.py
# ============================================================================
"""
RAG Factory - Singleton pattern untuk RAG components

FLOW:
1. Load embeddings (OpenAI/HuggingFace)
2. Load vector database (ChromaDB)
3. Initialize SmartRetriever (dengan document aggregation)
4. Initialize LLM
5. Create QueryChain

Dipanggil oleh chat_router.py
"""

from langchain_openai import ChatOpenAI
from langchain_chroma import Chroma
from dotenv import load_dotenv

from informasional.core.config_loader import APP_CONFIG
from informasional.core.prompt_manager import get_system_prompt, get_query_prompt
from informasional.utils.smart_retriever import SmartRetriever, EnhancedQueryChain
from informasional.utils.embeddings import EmbeddingManager, EmbeddingModel

load_dotenv()

# Singleton instance
_query_chain = None


def build_llm():
    """Build LLM based on config"""
    llm_cfg = APP_CONFIG["llm"]
    provider = llm_cfg["provider"]
    
    if provider == "openai":
        cfg = llm_cfg["openai"]
        return ChatOpenAI(
            model=cfg["model"],
            temperature=cfg["temperature"],
            max_tokens=cfg["max_tokens"],
            streaming=cfg.get("streaming", False),
        )
    
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        cfg = llm_cfg["gemini"]
        return ChatGoogleGenerativeAI(
            model=cfg["model"],
            temperature=cfg["temperature"],
            max_output_tokens=cfg["max_tokens"],
        )
    
    elif provider == "ollama":
        from langchain_community.chat_models import ChatOllama
        cfg = llm_cfg["ollama"]
        return ChatOllama(
            model=cfg["model"],
            temperature=cfg["temperature"],
            num_predict=cfg["max_tokens"],
            system=cfg.get("system_prompt_prefix", ""),
        )
    
    else:
        raise ValueError(f"LLM provider tidak dikenali: {provider}")


def get_query_chain():
    """
    Get or create singleton query chain
    
    Flow:
    1. Load embeddings (OpenAI/HuggingFace)
    2. Load vector database (ChromaDB)
    3. Initialize SmartRetriever (DENGAN document aggregation)
    4. Initialize LLM
    5. Create query chain
    """
    global _query_chain

    if _query_chain is not None:
        return _query_chain

    print("\n" + "="*60)
    print("🔄 Initializing RAG Pipeline")
    print("="*60)

    # =========================
    # 1. Embeddings
    # =========================
    embedding_cfg = APP_CONFIG["embeddings"]
    
    if embedding_cfg["model"] == "openai":
        embedding_manager = EmbeddingManager(
            model_type=EmbeddingModel.OPENAI,
            config={
                "model_name": embedding_cfg["openai"]["model_name"],
                "dimensions": embedding_cfg["openai"].get("dimensions", 1536)
            },
        )
    elif embedding_cfg["model"] == "huggingface":
        embedding_manager = EmbeddingManager(
            model_type=EmbeddingModel.HUGGINGFACE,
            config={
                "model_name": embedding_cfg["huggingface"]["model_name"],
                "device": embedding_cfg["huggingface"].get("device", "cpu")
            },
        )
    else:
        raise ValueError(f"Embedding model tidak didukung: {embedding_cfg['model']}")
    
    embeddings = embedding_manager.get_embeddings()
    
    print(f"✅ Embedding: {embedding_cfg['model']}")
    print(f"   Model: {embedding_cfg[embedding_cfg['model']]['model_name']}")

    # =========================
    # 2. Vector Database (ChromaDB)
    # =========================
    chroma_cfg = APP_CONFIG["vectordb"]["chroma"]
    collection_metadata = {"hnsw:space": chroma_cfg.get("distance_function", "cosine")}
    
    vectorstore = Chroma(
        collection_name=chroma_cfg["collection_name"],
        embedding_function=embeddings,
        persist_directory=chroma_cfg["persist_directory"],
        collection_metadata=collection_metadata
    )
    
    # Check collection count
    collection_count = vectorstore._collection.count()
    
    print(f"✅ Vector DB: ChromaDB")
    print(f"   Collection: {chroma_cfg['collection_name']}")
    print(f"   Total vectors: {collection_count}")

    # =========================
    # 3. Smart Retriever (DENGAN Document Aggregation)
    # =========================
    retrieval_cfg = APP_CONFIG.get("retrieval", {})
    
    smart_retriever = SmartRetriever(
        vectorstore=vectorstore,
        embedding_function=embeddings,
        top_k=retrieval_cfg.get("top_k", 5),
        similarity_threshold=retrieval_cfg.get("similarity_threshold", 0.5),
        max_documents=retrieval_cfg.get("max_documents", 3),  # Max dokumen unik
        fetch_full_document=retrieval_cfg.get("fetch_full_document", True),  # KUNCI!
    )
    
    print(f"✅ Retriever: SmartRetriever with Document Aggregation")
    print(f"   Top-K: {retrieval_cfg.get('top_k', 5)}")
    print(f"   Similarity threshold: {retrieval_cfg.get('similarity_threshold', 0.5)}")
    print(f"   Max documents: {retrieval_cfg.get('max_documents', 3)}")
    print(f"   Fetch full document: {retrieval_cfg.get('fetch_full_document', True)}")

    # =========================
    # 4. LLM
    # =========================
    llm = build_llm()
    print(f"✅ LLM: {APP_CONFIG['llm']['provider']}")

    # =========================
    # 5. Query Chain
    # =========================
    _query_chain = EnhancedQueryChain(
        smart_retriever=smart_retriever,
        llm=llm,
        system_prompt=get_system_prompt(),
        query_prompt=get_query_prompt(),
    )

    print("="*60)
    print("✅ RAG Pipeline READY")
    print("="*60 + "\n")
    
    return _query_chain


def reset_query_chain():
    """Reset singleton (useful untuk testing atau reload config)"""
    global _query_chain
    _query_chain = None
    print("🔄 Query chain reset")


def get_vectorstore_info():
    """Get info tentang vectorstore (untuk debugging)"""
    chain = get_query_chain()
    retriever = chain.retriever
    
    return retriever.get_collection_info()