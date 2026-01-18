# ============================================================================
# FILE: informasional/utils/smart_retriever.py
# REFACTORED - Terintegrasi dengan singleton EmbeddingManager & VectorStoreManager
# ============================================================================
"""
Smart Retriever dengan Document Aggregation

FLOW:
1. User query → embed query (via singleton EmbeddingManager)
2. Search ChromaDB → get top-K chunks (via singleton VectorStoreManager)
3. Extract unique document_ids
4. Fetch ALL chunks untuk setiap document_id
5. Sort by chunk_index
6. Merge chunks → dokumen lengkap
7. Return context ke LLM

INTEGRASI:
- Menggunakan EmbeddingManager singleton (sama dengan embedding router)
- Menggunakan VectorStoreManager singleton (sama dengan embedding router)
- Config dari config.yaml via ConfigLoader
"""

from typing import List, Dict, Any, Optional
from collections import defaultdict
import numpy as np
from langchain_core.documents import Document

from informasional.utils.embedding_utils import get_embedding_manager
from informasional.utils.vectorstore_utils import get_vectorstore
from informasional.core.config_loader import get_config


class SmartRetriever:
    """
    Smart Retriever dengan Document Aggregation
    
    KUNCI: Menggunakan SINGLETON managers untuk konsistensi dengan embedding.
    
    Features:
    - Document aggregation: fetch semua chunks dari dokumen yang sama
    - Similarity filtering: filter berdasarkan threshold
    - Metadata filtering: filter by jenjang, cabang, tahun
    """
    
    def __init__(
        self,
        config_path: str = None,
        top_k: int = None,
        similarity_threshold: float = None,
        max_documents: int = None,
        fetch_full_document: bool = None
    ):
        """
        Initialize SmartRetriever
        
        Args:
            config_path: Path ke config.yaml (optional, uses singleton)
            top_k: Override top_k from config
            similarity_threshold: Override threshold from config
            max_documents: Override max_documents from config
            fetch_full_document: Override fetch_full_document from config
        """
        # Load config
        self._config = get_config(config_path)
        retrieval_cfg = self._config.get_retrieval()
        
        # Get singleton managers (SAMA dengan embedding router)
        self._embedding_manager = get_embedding_manager(config_path)
        self._vectorstore_manager = get_vectorstore(config_path)
        
        # Retrieval settings (from config or override)
        self.top_k = top_k or retrieval_cfg.get("top_k", 10)
        self.similarity_threshold = similarity_threshold or retrieval_cfg.get("similarity_threshold", 0.4)
        self.max_documents = max_documents or retrieval_cfg.get("max_documents", 3)
        self.fetch_full_document = fetch_full_document if fetch_full_document is not None else retrieval_cfg.get("fetch_full_document", True)
        
        # Log config
        self._log_config()
    
    def _log_config(self):
        """Log current configuration"""
        print(f"🔍 SmartRetriever initialized")
        print(f"   └─ top_k: {self.top_k}")
        print(f"   └─ similarity_threshold: {self.similarity_threshold}")
        print(f"   └─ max_documents: {self.max_documents}")
        print(f"   └─ fetch_full_document: {self.fetch_full_document}")
        print(f"   └─ Using singleton EmbeddingManager: {self._embedding_manager.model_name}")
    
    @property
    def collection(self):
        """Get ChromaDB collection"""
        return self._vectorstore_manager.collection
    
    @property
    def embedding_manager(self):
        """Get EmbeddingManager (same as embedding router)"""
        return self._embedding_manager
    
    @property
    def vectorstore_manager(self):
        """Get VectorStoreManager (same as embedding router)"""
        return self._vectorstore_manager
    
    # =========================================================================
    # MAIN RETRIEVE METHOD
    # =========================================================================
    
    def retrieve(
        self,
        query: str,
        filter: Dict[str, Any] = None,
        verbose: bool = False
    ) -> List[Document]:
        """
        Retrieve dan aggregate documents
        
        Args:
            query: User query
            filter: Optional metadata filter (e.g., {"jenjang": "TK"})
            verbose: Print debug info
        
        Returns:
            List[Document] dengan chunks yang sudah digabungkan per dokumen
        """
        if verbose:
            print(f"\n{'='*60}")
            print("🔍 SMART RETRIEVAL PIPELINE")
            print(f"{'='*60}")
            print(f"📝 Query: '{query}'")
            if filter:
                print(f"🔎 Filter: {filter}")
        
        # 1️⃣ Embed query (menggunakan SAMA embedding dengan saat embed)
        query_embedding = self._embedding_manager.embed_query(query)
        
        if verbose:
            print(f"✅ Query embedded ({len(query_embedding)} dims)")
        
        # 2️⃣ Search top-K dari ChromaDB
        results = self._search_collection(query_embedding, filter)
        
        if not results['ids'][0]:
            if verbose:
                print("❌ No results found")
            return []
        
        # 3️⃣ Process results dan filter by similarity
        relevant_docs = self._process_results(results, verbose)
        
        if not relevant_docs:
            if verbose:
                print("❌ No documents passed similarity threshold")
            return []
        
        # 4️⃣ Aggregate by document_id (fetch full documents)
        if self.fetch_full_document:
            aggregated = self._aggregate_by_document(relevant_docs, verbose)
            return aggregated
        else:
            return relevant_docs
    
    def _search_collection(
        self,
        query_embedding: List[float],
        filter: Dict[str, Any] = None
    ) -> Dict:
        """Search ChromaDB collection"""
        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": self.top_k,
            "include": ["documents", "metadatas", "distances"]
        }
        
        if filter:
            kwargs["where"] = filter
        
        return self.collection.query(**kwargs)
    
    def _process_results(
        self,
        results: Dict,
        verbose: bool
    ) -> List[Document]:
        """Process initial query results dan filter by similarity"""
        docs = []
        seen = set()
        
        if verbose:
            print(f"\n📊 Processing {len(results['ids'][0])} initial results...")
        
        for i, (doc_id, distance, content, metadata) in enumerate(zip(
            results['ids'][0],
            results['distances'][0],
            results['documents'][0],
            results['metadatas'][0]
        )):
            # Convert distance to similarity (cosine distance to similarity)
            # ChromaDB cosine distance is in [0, 2], similarity = 1 - (distance / 2)
            similarity = 1 - (distance / 2)
            
            # Filter by threshold
            if similarity < self.similarity_threshold:
                if verbose:
                    print(f"   ⏭️ [{i+1}] Skipping (score {similarity:.3f} < {self.similarity_threshold})")
                continue
            
            # Deduplicate by chunk_id
            chunk_id = metadata.get('chunk_id', doc_id)
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            
            # Add retrieval metadata
            metadata['similarity_score'] = similarity
            metadata['retrieval_rank'] = i + 1
            
            docs.append(Document(
                page_content=content,
                metadata=metadata
            ))
            
            if verbose:
                print(f"   ✅ [{i+1}] Score: {similarity:.3f} | Doc: {metadata.get('document_id', 'N/A')[:30]} | Chunk: {metadata.get('chunk_index', '?')}/{metadata.get('total_chunks', '?')}")
        
        if verbose:
            print(f"\n✅ {len(docs)} chunks passed similarity threshold")
        
        return docs
    
    def _aggregate_by_document(
        self,
        initial_docs: List[Document],
        verbose: bool
    ) -> List[Document]:
        """
        🔑 KUNCI: Fetch ALL chunks dari dokumen yang sama
        
        Flow:
        1. Group by document_id
        2. Sort by max similarity score
        3. Limit to max_documents
        4. Fetch ALL chunks untuk setiap document
        5. Merge chunks
        """
        # Group by document_id
        docs_by_id: Dict[str, List[Document]] = defaultdict(list)
        doc_scores: Dict[str, float] = {}
        
        for doc in initial_docs:
            doc_id = doc.metadata.get('document_id')
            if not doc_id:
                doc_id = doc.metadata.get('source', 'unknown')
            
            docs_by_id[doc_id].append(doc)
            
            # Track max score per document
            score = doc.metadata.get('similarity_score', 0)
            if doc_id not in doc_scores or score > doc_scores[doc_id]:
                doc_scores[doc_id] = score
        
        # Sort by score, limit to max_documents
        sorted_doc_ids = sorted(
            docs_by_id.keys(),
            key=lambda x: doc_scores.get(x, 0),
            reverse=True
        )[:self.max_documents]
        
        if verbose:
            print(f"\n📚 Aggregating {len(sorted_doc_ids)} documents (max: {self.max_documents})")
        
        # Fetch ALL chunks for each document
        aggregated: List[Document] = []
        
        for doc_id in sorted_doc_ids:
            if verbose:
                print(f"\n   🔄 Fetching all chunks for: {doc_id[:40]}...")
            
            # Fetch ALL chunks untuk document_id ini dari ChromaDB
            all_chunks = self._fetch_all_chunks(doc_id)
            
            if all_chunks:
                merged = self._merge_chunks(all_chunks, doc_scores.get(doc_id, 0))
                aggregated.append(merged)
                
                if verbose:
                    print(f"      ✅ Merged {len(all_chunks)} chunks → {len(merged.page_content)} chars")
        
        return aggregated
    
    def _fetch_all_chunks(self, document_id: str) -> List[Document]:
        """
        Fetch ALL chunks dengan document_id yang sama dari ChromaDB
        
        Menggunakan VectorStoreManager.get_by_document_id()
        """
        try:
            # Use vectorstore manager method
            chunks_data = self._vectorstore_manager.get_by_document_id(document_id)
            
            if not chunks_data:
                return []
            
            # Convert to Document objects
            chunks = []
            for chunk_data in chunks_data:
                chunks.append(Document(
                    page_content=chunk_data["content"],
                    metadata=chunk_data["metadata"]
                ))
            
            # Already sorted by chunk_index in get_by_document_id
            return chunks
            
        except Exception as e:
            print(f"⚠️ Error fetching chunks for {document_id}: {e}")
            return []
    
    def _merge_chunks(
        self,
        chunks: List[Document],
        max_similarity: float
    ) -> Document:
        """Merge multiple chunks menjadi satu dokumen"""
        if not chunks:
            return None
        
        # Sort by chunk_index
        sorted_chunks = sorted(
            chunks,
            key=lambda x: x.metadata.get('chunk_index', 0)
        )
        
        # Combine content
        combined_content = "\n\n".join([
            c.page_content for c in sorted_chunks
        ])
        
        # Use first chunk metadata as base
        base_metadata = sorted_chunks[0].metadata.copy()
        base_metadata.update({
            'merged_chunks': len(sorted_chunks),
            'chunk_indices': [c.metadata.get('chunk_index', 0) for c in sorted_chunks],
            'similarity_score': max_similarity,
            'is_aggregated': True,
            'total_length': len(combined_content)
        })
        
        return Document(
            page_content=combined_content,
            metadata=base_metadata
        )
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get collection info (delegates to VectorStoreManager)"""
        return self._vectorstore_manager.get_collection_info()
    
    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter: Dict[str, Any] = None
    ) -> List[Document]:
        """
        Simple similarity search (tanpa aggregation)
        
        Untuk backward compatibility atau simple use cases
        """
        return self._vectorstore_manager.similarity_search(
            query=query,
            k=k,
            filter=filter
        )
    
    def similarity_search_with_score(
        self,
        query: str,
        k: int = 5,
        filter: Dict[str, Any] = None
    ) -> List[tuple]:
        """
        Similarity search with scores
        """
        return self._vectorstore_manager.similarity_search_with_score(
            query=query,
            k=k,
            filter=filter
        )


# =============================================================================
# SINGLETON PATTERN
# =============================================================================

_smart_retriever_instance: Optional[SmartRetriever] = None


def get_smart_retriever(config_path: str = None) -> SmartRetriever:
    """
    Get singleton SmartRetriever instance
    
    Args:
        config_path: Path ke config.yaml
    
    Returns:
        SmartRetriever singleton instance
    """
    global _smart_retriever_instance
    
    if _smart_retriever_instance is None:
        print("🔧 Initializing SmartRetriever...")
        _smart_retriever_instance = SmartRetriever(config_path=config_path)
    
    return _smart_retriever_instance


def reset_smart_retriever():
    """Reset singleton instance"""
    global _smart_retriever_instance
    _smart_retriever_instance = None
    print("🔄 SmartRetriever reset")