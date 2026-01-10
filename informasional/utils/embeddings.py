# ============================================================================
# utils/embeddings.py
# ============================================================================

import time
from enum import Enum
from typing import List

from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings

class EmbeddingModel(Enum):
    """Model embedding yang tersedia"""
    OPENAI = "openai"
    HUGGINGFACE = "huggingface"


class EmbeddingManager:
    """
    Manager untuk multiple embedding models
    
    Supports:
    - OpenAI embeddings (cloud-based)
    - HuggingFace embeddings (local)
    """
    
    def __init__(
        self,
        model_type: EmbeddingModel = EmbeddingModel.OPENAI,
        config: dict = None
    ):
        self.model_type = model_type
        self.config = config or {}
        self.embeddings = self._initialize_embeddings()
    
    def _initialize_embeddings(self):
        """Initialize embedding model based on type"""
        
        if self.model_type == EmbeddingModel.OPENAI:
            print("🔤 Initializing OpenAI Embeddings...")
            
            model_name = self.config.get(
                'model_name',
                'text-embedding-3-small'
            )
            
            return OpenAIEmbeddings(
                model=model_name,
                dimensions=self.config.get('dimensions', 1536)
            )
        
        elif self.model_type == EmbeddingModel.HUGGINGFACE:
            print("🔤 Initializing HuggingFace Embeddings...")
            
            model_name = self.config.get(
                'model_name',
                'sentence-transformers/all-MiniLM-L6-v2'
            )
            
            device = self.config.get('device', 'cpu')
            
            return HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs={'device': device},
                encode_kwargs={'normalize_embeddings': True}
            )
        
        else:
            raise ValueError(f"Unsupported embedding model: {self.model_type}")
    
    def get_embeddings(self):
        """Get initialized embeddings object"""
        return self.embeddings
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple documents
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        print(f"📊 Embedding {len(texts)} documents...")
        start_time = time.time()
        
        embeddings = self.embeddings.embed_documents(texts)
        
        processing_time = time.time() - start_time
        print(f"✅ Embedded in {processing_time:.2f}s")
        
        return embeddings
    
    def embed_query(self, text: str) -> List[float]:
        """
        Embed a single query
        
        Args:
            text: Query text
            
        Returns:
            Embedding vector
        """
        return self.embeddings.embed_query(text)
    
    def get_embedding_dimension(self) -> int:
        """Get embedding dimension"""
        if self.model_type == EmbeddingModel.OPENAI:
            return self.config.get('dimensions', 1536)
        elif self.model_type == EmbeddingModel.HUGGINGFACE:
            return self.config.get('dimensions', 384)  # Default for all-MiniLM-L6-v2
        return None