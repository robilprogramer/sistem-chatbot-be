
"""
VectorStore Manager - ChromaDB dengan konfigurasi dari YAML

Features:
1. Singleton pattern - sama instance untuk embed & retrieval
2. Config dari YAML file
3. Konsisten dengan EmbeddingManager
"""

from typing import Dict, Any, List, Optional
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

from informasional.utils.embedding_utils import (
    get_embedding_manager,
    sanitize_metadata_for_chroma
)


# =============================================================================
# VECTORSTORE MANAGER
# =============================================================================

class VectorStoreManager:
    """
    Centralized VectorStore Manager for ChromaDB
    
    PENTING: Gunakan get_vectorstore() untuk mendapatkan singleton instance.
    Ini memastikan vectorstore yang sama digunakan untuk:
    - Embedding storage
    - Retrieval search
    - Document aggregation
    """
    
    def __init__(self, config_path: str = None):
        """
        Initialize VectorStoreManager
        
        Args:
            config_path: Path ke config.yaml
        """
        # Get embedding manager (singleton)
        self._embedding_manager = get_embedding_manager(config_path)
        
        # Get ChromaDB config
        self._chroma_cfg = self._embedding_manager.get_chroma_config()
        
        # Initialize ChromaDB
        self._vectorstore = self._initialize_vectorstore()
        
        # Log
        self._log_config()
    
    def _log_config(self):
        """Log configuration"""
        print(f"📦 VectorStoreManager initialized")
        print(f"   └─ Collection: {self._chroma_cfg['collection_name']}")
        print(f"   └─ Persist Dir: {self._chroma_cfg['persist_directory']}")
        print(f"   └─ Distance: {self._chroma_cfg.get('distance_function', 'cosine')}")
    
    def _initialize_vectorstore(self) -> Chroma:
        """Initialize ChromaDB vectorstore"""
        
        # Collection metadata dengan distance function
        collection_metadata = {
            "hnsw:space": self._chroma_cfg.get("distance_function", "cosine")
        }
        
        return Chroma(
            collection_name=self._chroma_cfg["collection_name"],
            persist_directory=self._chroma_cfg["persist_directory"],
            embedding_function=self._embedding_manager.get_embeddings(),
            collection_metadata=collection_metadata
        )
    
    # =========================================================================
    # PUBLIC METHODS
    # =========================================================================
    
    @property
    def vectorstore(self) -> Chroma:
        """Get underlying Chroma vectorstore"""
        return self._vectorstore
    
    @property
    def collection(self):
        """Get ChromaDB collection"""
        return self._vectorstore._collection
    
    @property
    def embedding_manager(self):
        """Get associated EmbeddingManager"""
        return self._embedding_manager
    
    def add_documents(
        self,
        documents: List[Document],
        ids: List[str] = None
    ) -> List[str]:
        """
        Add documents to vectorstore
        
        Args:
            documents: List of LangChain Document objects
            ids: Optional list of IDs (will be generated if not provided)
        
        Returns:
            List of document IDs
        """
        if not documents:
            return []
        
        # Sanitize metadata
        for doc in documents:
            doc.metadata = sanitize_metadata_for_chroma(doc.metadata)
        
        # Add to vectorstore
        if ids:
            return self._vectorstore.add_documents(documents, ids=ids)
        else:
            return self._vectorstore.add_documents(documents)
    
    def add_texts(
        self,
        texts: List[str],
        metadatas: List[Dict[str, Any]] = None,
        ids: List[str] = None
    ) -> List[str]:
        """
        Add texts with metadata to vectorstore
        
        Args:
            texts: List of text contents
            metadatas: List of metadata dicts
            ids: Optional list of IDs
        
        Returns:
            List of document IDs
        """
        if not texts:
            return []
        
        # Sanitize metadata
        if metadatas:
            metadatas = [sanitize_metadata_for_chroma(m) for m in metadatas]
        
        return self._vectorstore.add_texts(
            texts=texts,
            metadatas=metadatas,
            ids=ids
        )
    
    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter: Dict[str, Any] = None
    ) -> List[Document]:
        """
        Search for similar documents
        
        Args:
            query: Search query
            k: Number of results
            filter: Optional metadata filter
        
        Returns:
            List of similar documents
        """
        return self._vectorstore.similarity_search(
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
        Search with similarity scores
        
        Args:
            query: Search query
            k: Number of results
            filter: Optional metadata filter
        
        Returns:
            List of (Document, score) tuples
        """
        return self._vectorstore.similarity_search_with_score(
            query=query,
            k=k,
            filter=filter
        )
    
    def delete(self, ids: List[str]) -> None:
        """
        Delete documents by IDs
        
        Args:
            ids: List of document IDs to delete
        """
        if ids:
            self._vectorstore.delete(ids=ids)
    
    def delete_by_filter(self, filter: Dict[str, Any]) -> int:
        """
        Delete documents matching filter
        
        Args:
            filter: Metadata filter (e.g., {"document_id": "xxx"})
        
        Returns:
            Number of deleted documents
        """
        try:
            # Get matching IDs
            results = self.collection.get(
                where=filter,
                include=[]
            )
            
            if results['ids']:
                self._vectorstore.delete(ids=results['ids'])
                return len(results['ids'])
            
            return 0
        except Exception as e:
            print(f"⚠️ Delete by filter error: {e}")
            return 0
    
    def get_by_document_id(self, document_id: str) -> List[Dict[str, Any]]:
        """
        Get all chunks for a document_id
        
        Args:
            document_id: Document tracking ID
        
        Returns:
            List of chunk data with content and metadata
        """
        try:
            results = self.collection.get(
                where={"document_id": document_id},
                include=["documents", "metadatas"]
            )
            
            if not results['ids']:
                return []
            
            chunks = []
            for i, (chunk_id, content, metadata) in enumerate(zip(
                results['ids'],
                results['documents'],
                results['metadatas']
            )):
                chunks.append({
                    "chroma_id": chunk_id,
                    "content": content,
                    "metadata": metadata,
                    "chunk_index": metadata.get('chunk_index', i)
                })
            
            # Sort by chunk_index
            chunks.sort(key=lambda x: x['chunk_index'])
            
            return chunks
            
        except Exception as e:
            print(f"⚠️ Get by document_id error: {e}")
            return []
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get collection statistics"""
        collection = self.collection
        count = collection.count()
        
        # Get unique document_ids
        unique_docs = set()
        if count > 0:
            try:
                results = collection.get(include=['metadatas'])
                for meta in results.get('metadatas', []):
                    if meta and 'document_id' in meta:
                        unique_docs.add(meta['document_id'])
            except:
                pass
        
        return {
            "collection_name": collection.name,
            "total_vectors": count,
            "unique_documents": len(unique_docs),
            "document_ids_sample": list(unique_docs)[:20],
            "distance_function": collection.metadata.get("hnsw:space", "unknown"),
            "embedding_model": self._embedding_manager.model_name,
            "embedding_dimension": self._embedding_manager.get_dimension()
        }
    
    def as_retriever(self, search_kwargs: Dict[str, Any] = None):
        """
        Get LangChain retriever
        
        Args:
            search_kwargs: Search parameters (k, filter, etc.)
        
        Returns:
            LangChain VectorStoreRetriever
        """
        kwargs = search_kwargs or {"k": 5}
        return self._vectorstore.as_retriever(search_kwargs=kwargs)


# =============================================================================
# SINGLETON PATTERN
# =============================================================================

_vectorstore_manager_instance: Optional[VectorStoreManager] = None


def get_vectorstore(config_path: str = None) -> VectorStoreManager:
    """
    Get singleton VectorStoreManager instance
    
    PENTING: Selalu gunakan fungsi ini untuk mendapatkan VectorStoreManager.
    Ini memastikan vectorstore yang SAMA digunakan untuk:
    - Embedding router (add documents)
    - Retrieval router (search)
    - Chat service (RAG)
    
    Args:
        config_path: Path ke config.yaml (required on first call)
    
    Returns:
        VectorStoreManager singleton instance
    """
    global _vectorstore_manager_instance
    
    if _vectorstore_manager_instance is None:
        print(f"🔧 Initializing VectorStoreManager...")
        _vectorstore_manager_instance = VectorStoreManager(config_path=config_path)
    
    return _vectorstore_manager_instance


def reset_vectorstore():
    """Reset singleton instance"""
    global _vectorstore_manager_instance
    _vectorstore_manager_instance = None
    print("🔄 VectorStoreManager reset")