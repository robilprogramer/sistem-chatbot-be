
"""
RAG Factory - Singleton pattern untuk semua RAG components

INTEGRASI:
- ConfigLoader (singleton)
- EmbeddingManager (singleton) 
- VectorStoreManager (singleton)
- SmartRetriever (singleton)
- LLM (built from config)
- QueryChain (singleton)

Semua component menggunakan CONFIG YANG SAMA dari config.yaml
"""

import os
from typing import Dict, Any, Optional
from dotenv import load_dotenv

from langchain_core.language_models import BaseChatModel

from informasional.core.config_loader import get_config
from informasional.utils.embedding_utils import get_embedding_manager
from informasional.utils.vectorstore_utils import get_vectorstore
from informasional.utils.smart_retriever import get_smart_retriever

load_dotenv()


# =============================================================================
# LLM BUILDER
# =============================================================================

def build_llm(config_path: str = None) -> BaseChatModel:
    """
    Build LLM based on config
    
    Supports:
    - OpenAI (ChatGPT)
    - Google Gemini
    - Ollama (local)
    """
    config = get_config(config_path)
    llm_cfg = config.get_llm()
    provider = llm_cfg.get("provider", "openai")
    
    print(f"🤖 Building LLM: {provider}")
    
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        
        cfg = llm_cfg.get("openai", {})
        return ChatOpenAI(
            model=cfg.get("model", "gpt-4o-mini"),
            temperature=cfg.get("temperature", 0),
            max_tokens=cfg.get("max_tokens", 1024),
            streaming=cfg.get("streaming", False),
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
    
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        cfg = llm_cfg.get("gemini", {})
        return ChatGoogleGenerativeAI(
            model=cfg.get("model", "gemini-2.0-flash"),
            temperature=cfg.get("temperature", 0),
            max_output_tokens=cfg.get("max_tokens", 1024),
            google_api_key=os.getenv("GOOGLE_API_KEY")
        )
    
    elif provider == "ollama":
        from langchain_community.chat_models import ChatOllama
        
        cfg = llm_cfg.get("ollama", {})
        return ChatOllama(
            model=cfg.get("model", "llama3"),
            temperature=cfg.get("temperature", 0),
            num_predict=cfg.get("max_tokens", 1024)
        )
    
    else:
        raise ValueError(f"LLM provider tidak dikenali: {provider}")


# =============================================================================
# QUERY CHAIN
# =============================================================================

class QueryChain:
    """
    RAG Query Chain
    
    Menggabungkan:
    - SmartRetriever (dengan document aggregation)
    - LLM
    - Prompts dari config
    """
    
    def __init__(
        self,
        retriever,
        llm: BaseChatModel,
        system_prompt: str,
        query_prompt: str,
        no_context_response: str,
        low_relevance_response: str
    ):
        self.retriever = retriever
        self.llm = llm
        self.system_prompt = system_prompt
        self.query_prompt = query_prompt
        self.no_context_response = no_context_response
        self.low_relevance_response = low_relevance_response
    
    def query(
        self,
        question: str,
        filter: Dict[str, Any] = None,
        verbose: bool = False
    ) -> Dict[str, Any]:
        """
        Execute RAG query
        
        Args:
            question: User question
            filter: Optional metadata filter
            verbose: Print debug info
        
        Returns:
            {
                'answer': str,
                'sources': List[Dict],
                'metadata': Dict
            }
        """
        if verbose:
            print(f"\n🚀 RAG PIPELINE")
            print(f"❓ Question: {question}")
        
        # 1️⃣ Retrieve (dengan document aggregation)
        docs = self.retriever.retrieve(question, filter=filter, verbose=verbose)
        
        # 2️⃣ Check if we have results
        if not docs:
            return {
                'answer': self.no_context_response,
                'sources': [],
                'metadata': {
                    'num_sources': 0,
                    'relevance_check': 'FAILED - No documents found'
                }
            }
        
        # 3️⃣ Check similarity scores
        similarities = [doc.metadata.get('similarity_score', 0) for doc in docs]
        avg_similarity = sum(similarities) / len(similarities) if similarities else 0
        max_similarity = max(similarities) if similarities else 0
        
        if verbose:
            print(f"\n📊 Similarity: avg={avg_similarity:.3f}, max={max_similarity:.3f}")
        
        # Low relevance check
        if avg_similarity < 0.5:
            return {
                'answer': self.low_relevance_response,
                'sources': self._build_sources(docs),
                'metadata': {
                    'num_sources': len(docs),
                    'avg_similarity': float(avg_similarity),
                    'max_similarity': float(max_similarity),
                    'relevance_check': 'FAILED - Low similarity'
                }
            }
        
        # 4️⃣ Build context
        context = self._build_context(docs)
        
        if verbose:
            print(f"\n📝 Context: {len(context)} chars from {len(docs)} documents")
        
        # 5️⃣ Generate answer
        full_prompt = self._build_prompt(question, context)
        
        if verbose:
            print(f"\n🤖 Calling LLM...")
        
        response = self.llm.invoke(full_prompt)
        answer = response.content
        
        # 6️⃣ Build response
        return {
            'answer': answer,
            'sources': self._build_sources(docs),
            'metadata': {
                'num_sources': len(docs),
                'avg_similarity': float(avg_similarity),
                'max_similarity': float(max_similarity),
                'total_context_length': len(context),
                'relevance_check': 'PASSED'
            }
        }
    
    def _build_prompt(self, question: str, context: str) -> str:
        """Build full prompt for LLM"""
        query_part = self.query_prompt.format(
            question=question,
            context=context
        )
        return f"{self.system_prompt}\n\n{query_part}"
    
    def _build_context(self, docs) -> str:
        """Build context string from documents"""
        parts = []
        
        for i, doc in enumerate(docs, 1):
            meta = doc.metadata
            
            # Build header
            header_parts = [f"[Dokumen {i}]"]
            
            if meta.get('source'):
                header_parts.append(f"Sumber: {meta['source']}")
            if meta.get('jenjang'):
                header_parts.append(f"Jenjang: {meta['jenjang']}")
            if meta.get('tahun'):
                header_parts.append(f"Tahun: {meta['tahun']}")
            if meta.get('cabang'):
                header_parts.append(f"Cabang: {meta['cabang']}")
            if meta.get('similarity_score'):
                header_parts.append(f"Relevansi: {meta['similarity_score']:.0%}")
            if meta.get('merged_chunks', 1) > 1:
                header_parts.append(f"({meta['merged_chunks']} bagian digabung)")
            
            header = " | ".join(header_parts)
            parts.append(f"{header}\n\n{doc.page_content}")
        
        return "\n\n" + "="*50 + "\n\n".join(parts)
    
    def _build_sources(self, docs) -> list:
        """Build sources list for response"""
        sources = []
        for doc in docs:
            meta = doc.metadata
            sources.append({
                'source': meta.get('source', 'Unknown'),
                'document_id': meta.get('document_id', 'Unknown'),
                'jenjang': meta.get('jenjang', ''),
                'cabang': meta.get('cabang', ''),
                'tahun': meta.get('tahun', ''),
                'similarity': meta.get('similarity_score', 0),
                'merged_chunks': meta.get('merged_chunks', 1),
                'is_aggregated': meta.get('is_aggregated', False)
            })
        return sources


# =============================================================================
# SINGLETON QUERY CHAIN
# =============================================================================

_query_chain_instance: Optional[QueryChain] = None


def get_query_chain(config_path: str = None) -> QueryChain:
    """
    Get or create singleton QueryChain
    
    INTEGRASI:
    - Menggunakan singleton SmartRetriever
    - SmartRetriever menggunakan singleton EmbeddingManager & VectorStoreManager
    - Semua config dari config.yaml
    """
    global _query_chain_instance
    
    if _query_chain_instance is not None:
        return _query_chain_instance
    
    print("\n" + "="*60)
    print("🔄 Initializing RAG Pipeline")
    print("="*60)
    
    # Load config
    config = get_config(config_path)
    
    # 1️⃣ Get SmartRetriever (singleton)
    # Ini akan otomatis initialize:
    # - EmbeddingManager (singleton)
    # - VectorStoreManager (singleton)
    retriever = get_smart_retriever(config_path)
    
    # Log info
    collection_info = retriever.get_collection_info()
    print(f"✅ Retriever ready")
    print(f"   └─ Collection: {collection_info.get('total_vectors', 0)} vectors")
    print(f"   └─ Documents: {collection_info.get('unique_documents', 0)} unique")
    
    # 2️⃣ Build LLM
    llm = build_llm(config_path)
    llm_cfg = config.get_llm()
    print(f"✅ LLM: {llm_cfg.get('provider', 'unknown')}")
    
    # 3️⃣ Get prompts
    prompts = config.get_informational_prompts()
    print(f"✅ Prompts loaded")
    
    # 4️⃣ Create QueryChain
    _query_chain_instance = QueryChain(
        retriever=retriever,
        llm=llm,
        system_prompt=prompts['system_prompt'],
        query_prompt=prompts['query_prompt'],
        no_context_response=prompts['no_context_response'],
        low_relevance_response=prompts['low_relevance_response']
    )
    
    print("="*60)
    print("✅ RAG Pipeline READY")
    print("="*60 + "\n")
    
    return _query_chain_instance


def reset_query_chain():
    """Reset singleton (useful untuk testing atau reload config)"""
    global _query_chain_instance
    _query_chain_instance = None
    print("🔄 Query chain reset")


def get_vectorstore_info() -> Dict[str, Any]:
    """Get vectorstore info (untuk debugging)"""
    chain = get_query_chain()
    return chain.retriever.get_collection_info()