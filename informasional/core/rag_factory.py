from langchain_openai import ChatOpenAI
from langchain_chroma import Chroma
from core.config_loader import APP_CONFIG
from core.prompt_manager import get_system_prompt, get_query_prompt
from dotenv import load_dotenv

from utils.smart_retriever import SmartRetriever, EnhancedQueryChain
from utils.embeddings import EmbeddingManager, EmbeddingModel

load_dotenv()

_query_chain = None  # Singleton


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
            streaming=cfg["streaming"],
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
    3. Initialize retriever
    4. Initialize LLM
    5. Create query chain
    """
    global _query_chain

    if _query_chain is not None:
        return _query_chain

    print("🔄 Initializing RAG (ONCE)")

    # =========================
    # Embeddings
    # =========================
    embedding_cfg = APP_CONFIG["embeddings"]
    
    if embedding_cfg["model"] == "openai":
        embedding_manager = EmbeddingManager(
            model_type=EmbeddingModel.OPENAI,
            config={
                "model_name": embedding_cfg["openai"]["model_name"],
                "dimensions": embedding_cfg["openai"]["dimensions"]
            },
        )
    elif embedding_cfg["model"] == "huggingface":
        embedding_manager = EmbeddingManager(
            model_type=EmbeddingModel.HUGGINGFACE,
            config={
                "model_name": embedding_cfg["huggingface"]["model_name"],
                "device": embedding_cfg["huggingface"]["device"]
            },
        )
    else:
        raise ValueError(f"Embedding model tidak didukung: {embedding_cfg['model']}")
    
    embeddings = embedding_manager.get_embeddings()
    
    print(f"✅ Embedding: {embedding_cfg['model']}")
    print(f"   Model: {embedding_cfg[embedding_cfg['model']]['model_name']}")

    # =========================
    # Vector Database
    # =========================
    chroma_cfg = APP_CONFIG["vectordb"]["chroma"]
    collection_metadata = {"hnsw:space": chroma_cfg.get("distance_function", "cosine")}
    
    vectorstore = Chroma(
        collection_name=chroma_cfg["collection_name"],
        embedding_function=embeddings,
        persist_directory=chroma_cfg["persist_directory"],
        collection_metadata=collection_metadata
    )
    
    print(f"✅ Vector DB: ChromaDB")
    print(f"   Collection: {chroma_cfg['collection_name']}")

    # =========================
    # Retriever (Simplified)
    # =========================
    retrieval_cfg = APP_CONFIG["retrieval"]
    
    smart_retriever = SmartRetriever(
        vectorstore=vectorstore,
        embedding_function=embeddings,
        top_k=retrieval_cfg["top_k"],
        similarity_threshold=retrieval_cfg.get("similarity_threshold", 0.5),
        min_docs_required=2  # ✅ Minimal 2 dokumen
    )
    
    print(f"✅ Retriever initialized")
    print(f"   Top-K: {retrieval_cfg['top_k']}")
    print(f"   Similarity threshold: {retrieval_cfg.get('similarity_threshold', 0.5)}")

    # =========================
    # LLM
    # =========================
    llm = build_llm()
    print(f"✅ LLM: {APP_CONFIG['llm']['provider']}")

    # =========================
    # Query Chain
    # =========================
    _query_chain = EnhancedQueryChain(
        smart_retriever=smart_retriever,
        llm=llm,
        system_prompt=get_system_prompt(),
        query_prompt=get_query_prompt(),
        
    )

    print("✅ RAG READY\n")
    return _query_chain