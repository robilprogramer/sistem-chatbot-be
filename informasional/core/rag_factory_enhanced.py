# core/rag_factory_enhanced.py

"""
Enhanced RAG Factory
Integrates all RAG components with improved architecture
WITH CONVERSATION MEMORY SUPPORT
"""

from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_chroma import Chroma
from dotenv import load_dotenv

from core.config_loader import APP_CONFIG
from core.prompt_manager_enhanced import (
    get_system_prompt,
    get_query_prompt,
    get_conversation_context_prompt
)

from utils.db import SessionLocal
from repositories.master_repository import MasterRepository
from utils.query_processor import QueryProcessor
from utils.smart_retriever_enhanced import EnhancedSmartRetriever
from utils.enhanced_query_chain import EnhancedQueryChain, ConversationManager
from utils.embeddings import EmbeddingManager, EmbeddingModel

# NEW: Import conversation memory
from core.conversation_memory import (
    add_user_message, 
    add_assistant_message, 
    get_conversation_context
)

load_dotenv()

# Global instances (singleton pattern)
_query_chain = None
_conversation_manager = None


def build_llm():
    """
    Build LLM based on config
    Supports: OpenAI, Gemini, Ollama
    """
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
    Get or create RAG query chain (singleton)
    
    Returns:
        EnhancedQueryChain instance
    """
    global _query_chain

    if _query_chain is not None:
        return _query_chain

    print("\n" + "="*60)
    print("🚀 Initializing Enhanced RAG System")
    print("="*60)

    # =========================
    # 1. Database & Repositories
    # =========================
    print("\n📊 Step 1: Setting up repositories...")
    session = SessionLocal()
    master_repo = MasterRepository(session)
    print("   ✅ Master repository ready")

    # =========================
    # 2. Embeddings
    # =========================
    print("\n🔢 Step 2: Initializing embeddings...")
    
    # Choose embedding model
    # Option 1: HuggingFace (local, free)
    embedding_manager = EmbeddingManager(
        model_type=EmbeddingModel.HUGGINGFACE,
        config={"model_name": "sentence-transformers/all-MiniLM-L6-v2"},
    )
    
    # Option 2: OpenAI (cloud, paid but better)
    # embedding_manager = EmbeddingManager(
    #     model_type=EmbeddingModel.OPENAI,
    #     config={"model_name": "text-embedding-3-small"},
    # )
    
    embeddings = embedding_manager.get_embeddings()
    print("   ✅ Embeddings ready")

    # =========================
    # 3. Vector Store
    # =========================
    print("\n💾 Step 3: Loading vector store...")
    vectorstore = Chroma(
        collection_name="ypi_knowledge_base",
        embedding_function=embeddings,
        persist_directory="./chroma_db",
    )
    
    # Check collection size
    try:
        collection = vectorstore._collection
        count = collection.count()
        print(f"   ✅ Vector store ready: {count} documents")
    except:
        print(f"   ✅ Vector store ready")

    # =========================
    # 4. LLM
    # =========================
    print("\n🤖 Step 4: Building LLM...")
    llm = build_llm()
    print(f"   ✅ LLM ready: {APP_CONFIG['llm']['provider']}")

    # =========================
    # 5. Query Processor
    # =========================
    print("\n🔍 Step 5: Initializing query processor...")
    query_processor = QueryProcessor(
        master_repo=master_repo,
        llm=llm  # Optional: for advanced query rewriting
    )
    print("   ✅ Query processor ready")

    # =========================
    # 6. Smart Retriever
    # =========================
    print("\n🎯 Step 6: Setting up smart retriever...")
    smart_retriever = EnhancedSmartRetriever(
        vectorstore=vectorstore,
        query_processor=query_processor,
        top_k=5,
        use_hybrid=False,  # Set True to enable hybrid search
        enable_reranking=True,
        diversity_threshold=0.7
    )
    print("   ✅ Smart retriever ready")

    # =========================
    # 7. Query Chain
    # =========================
    print("\n🔗 Step 7: Building query chain...")
    _query_chain = EnhancedQueryChain(
        smart_retriever=smart_retriever,
        llm=llm,
        system_prompt=get_system_prompt(),
        query_prompt=get_query_prompt(),
        conversation_prompt=get_conversation_context_prompt()
    )
    print("   ✅ Query chain ready")

    print("\n" + "="*60)
    print("✅ RAG System Initialized Successfully!")
    print("="*60 + "\n")

    return _query_chain


def get_conversation_manager():
    """
    Get or create conversation manager (singleton)
    
    Returns:
        ConversationManager instance
    """
    global _conversation_manager
    
    if _conversation_manager is None:
        _conversation_manager = ConversationManager(max_history=10)
    
    return _conversation_manager


def reset_rag_system():
    """
    Reset RAG system (force re-initialization)
    Useful when config changes or for testing
    """
    global _query_chain, _conversation_manager
    
    print("🔄 Resetting RAG system...")
    _query_chain = None
    _conversation_manager = None
    print("✅ RAG system reset complete")


# =========================
# NEW: Enhanced Query Functions with Conversation Memory
# =========================

def query_rag_with_context(
    question: str,
    session_id: str,
    filters: dict = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Query RAG with automatic conversation context injection
    
    Args:
        question: User's question
        session_id: Session ID for conversation tracking
        filters: Optional metadata filters
        **kwargs: Additional parameters for query_chain
        
    Returns:
        Dict with answer, sources, and metadata
    """
    print(f"\n{'='*60}")
    print(f"💬 Query with Context")
    print(f"   Question: {question}")
    print(f"   Session: {session_id}")
    print(f"{'='*60}")
    
    # 1. Save user message to memory
    add_user_message(session_id, question)
    print("   ✅ User message saved to memory")
    
    # 2. Get conversation context (last 3 turns)
    context = get_conversation_context(session_id, max_turns=3)
    has_context = bool(context)
    
    if has_context:
        print("   ✅ Conversation context retrieved")
        print(f"   📝 Context length: {len(context)} chars")
    else:
        print("   ℹ️  No previous context (first message)")
    
    # 3. Enhance question with context
    if has_context:
        enhanced_question = f"""{context}

CURRENT QUESTION: {question}

INSTRUCTION: Consider the conversation history above. If the current question references previous topics, provide a contextually appropriate answer."""
        print("   ✅ Question enhanced with context")
    else:
        enhanced_question = question
    
    # 4. Query RAG system
    result = query_rag(
        question=enhanced_question,
        session_id=session_id,
        filters=filters,
        **kwargs
    )
    print("   ✅ RAG query completed")
    
    # 5. Save assistant response to memory
    add_assistant_message(session_id, result['answer'])
    print("   ✅ Assistant response saved to memory")
    
    # 6. Add metadata
    result['has_context'] = has_context
    result['session_id'] = session_id
    
    print(f"{'='*60}\n")
    
    return result


def query_rag(
    question: str,
    session_id: str = "default",
    filters: dict = None
) -> dict:
    """
    Original RAG query function (WITHOUT automatic context)
    Use this for backward compatibility or when context is already in question
    
    Args:
        question: User question (can be pre-enhanced with context)
        session_id: Session identifier for conversation tracking
        filters: Optional metadata filters
        
    Returns:
        Dict with answer and sources
    """
    # Get components
    query_chain = get_query_chain()
    conv_manager = get_conversation_manager()
    
    # Get conversation history (for legacy ConversationManager)
    history = conv_manager.get_history(session_id)
    
    # Query
    result = query_chain.query(
        question=question,
        filters=filters,
        conversation_history=history,
        session_id=session_id
    )
    
    # Update conversation history (for legacy ConversationManager)
    conv_manager.add_message(session_id, 'user', question)
    conv_manager.add_message(session_id, 'assistant', result['answer'])
    
    return result


# =========================
# Convenience Functions
# =========================

def clear_conversation(session_id: str = "default"):
    """
    Clear conversation history for a session
    Clears both new conversation_memory and legacy ConversationManager
    """
    from core.conversation_memory import clear_conversation as clear_memory
    
    # Clear new memory system
    clear_memory(session_id)
    
    # Clear legacy ConversationManager
    conv_manager = get_conversation_manager()
    conv_manager.clear_session(session_id)
    
    print(f"✅ Conversation cleared for session: {session_id}")


# =========================
# Testing Function
# =========================

def test_rag_system():
    """
    Test RAG system with sample queries
    """
    print("\n" + "="*60)
    print("🧪 Testing RAG System with Conversation Context")
    print("="*60)
    
    test_session = "test-conversation"
    
    # Test 1: First question
    print("\n### Test 1: Initial Question ###")
    result1 = query_rag_with_context(
        "Berapa biaya SD?",
        session_id=test_session
    )
    print(f"\n📝 Answer:\n{result1['answer']}\n")
    
    # Test 2: Follow-up (should use context)
    print("\n### Test 2: Follow-up Question (with context) ###")
    result2 = query_rag_with_context(
        "Kalau SMP?",
        session_id=test_session
    )
    print(f"\n📝 Answer:\n{result2['answer']}\n")
    print(f"Has Context: {result2['has_context']}")
    
    # Test 3: Another follow-up
    print("\n### Test 3: Another Follow-up ###")
    result3 = query_rag_with_context(
        "Ada beasiswa?",
        session_id=test_session
    )
    print(f"\n📝 Answer:\n{result3['answer']}\n")
    print(f"Has Context: {result3['has_context']}")
    
    # Clear test session
    clear_conversation(test_session)
    print("\n✅ Test completed and session cleared")


if __name__ == "__main__":
    # Run test if executed directly
    test_rag_system()