# ============================================================================
# FILE: api/embedding_router.py
# ============================================================================
"""
Embedding Router dengan Document ID Tracking

PERBAIKAN UTAMA:
1. Pastikan document_id SELALU ada di metadata
2. Sanitize metadata untuk ChromaDB
3. Track chunks yang di-embed
4. Support re-embedding
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import os
import yaml
import torch
from dotenv import load_dotenv
from typing import List, Dict, Any
from collections import defaultdict

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings


# ==============================
# Configuration
# ==============================
load_dotenv()


def load_config(config_path: str) -> Dict:
    """Load and resolve config"""
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    def resolve_env_vars(d):
        if isinstance(d, dict):
            return {k: resolve_env_vars(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [resolve_env_vars(v) for v in d]
        elif isinstance(d, str) and d.startswith("${") and d.endswith("}"):
            return os.getenv(d[2:-1], "")
        return d
    
    return resolve_env_vars(config)


def sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize metadata untuk ChromaDB
    ChromaDB hanya support: str, int, float, bool
    """
    safe = {}
    
    for k, v in metadata.items():
        if v is None:
            safe[k] = ""  # Convert None to empty string
        elif isinstance(v, bool):
            safe[k] = v
        elif isinstance(v, (int, float)):
            safe[k] = v
        elif isinstance(v, str):
            safe[k] = v
        elif isinstance(v, list):
            # Convert list to comma-separated string
            safe[k] = ", ".join(str(item) for item in v)
        elif isinstance(v, dict):
            # Flatten dict to string
            safe[k] = str(v)
        else:
            safe[k] = str(v)
    
    return safe


def validate_document_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validasi dan fix metadata yang WAJIB ada
    """
    required_fields = {
        'document_id': lambda m: m.get('source', 'unknown'),
        'chunk_id': lambda m: f"{m.get('document_id', 'doc')}_{m.get('chunk_index', 0)}",
        'chunk_index': lambda m: 0,
        'total_chunks': lambda m: 1,
        'source': lambda m: 'unknown',
    }
    
    validated = metadata.copy()
    
    for field, default_fn in required_fields.items():
        if field not in validated or validated[field] is None:
            validated[field] = default_fn(validated)
    
    return validated


# ==============================
# Embedding Manager Class
# ==============================
class EmbeddingManager:
    """
    Manages embeddings dan vector store operations
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.embeddings = self._build_embeddings()
        self.vectorstore = self._build_vectorstore()
    
    def _build_embeddings(self):
        """Build embedding function"""
        embedding_cfg = self.config["embeddings"]
        
        if embedding_cfg["model"] == "openai":
            return OpenAIEmbeddings(
                model=embedding_cfg["openai"]["model_name"],
                openai_api_key=os.getenv("OPENAI_API_KEY")
            )
        
        elif embedding_cfg["model"] == "huggingface":
            device = embedding_cfg["huggingface"].get("device", "cpu")
            if device == "cuda" and not torch.cuda.is_available():
                device = "cpu"
            
            return HuggingFaceEmbeddings(
                model_name=embedding_cfg["huggingface"]["model_name"],
                model_kwargs={"device": device},
                encode_kwargs={"normalize_embeddings": True}
            )
        
        else:
            raise RuntimeError(f"Embedding model tidak didukung: {embedding_cfg['model']}")
    
    def _build_vectorstore(self) -> Chroma:
        """Build ChromaDB vectorstore"""
        chroma_cfg = self.config["vectordb"]["chroma"]
        
        return Chroma(
            collection_name=chroma_cfg["collection_name"],
            persist_directory=chroma_cfg["persist_directory"],
            embedding_function=self.embeddings,
            collection_metadata={"hnsw:space": chroma_cfg.get("distance_function", "cosine")}
        )
    
    def embed_documents(self, documents: List[Document]) -> Dict[str, Any]:
        """
        Embed documents ke ChromaDB
        
        Args:
            documents: List of Document dengan metadata lengkap
            
        Returns:
            Dict dengan statistik embedding
        """
        if not documents:
            return {"message": "No documents to embed", "total": 0}
        
        # Validate dan sanitize metadata
        validated_docs: List[Document] = []
        chunk_ids: List[str] = []
        
        for doc in documents:
            # Validate metadata
            validated_meta = validate_document_metadata(doc.metadata)
            # Sanitize untuk ChromaDB
            safe_meta = sanitize_metadata(validated_meta)
            
            validated_docs.append(Document(
                page_content=doc.page_content,
                metadata=safe_meta
            ))
            
            chunk_ids.append(safe_meta['chunk_id'])
        
        # Add to ChromaDB dengan explicit IDs
        self.vectorstore.add_documents(
            documents=validated_docs,
            ids=chunk_ids
        )
        
        # Build statistics
        docs_by_id = defaultdict(int)
        for doc in validated_docs:
            docs_by_id[doc.metadata.get('document_id', 'unknown')] += 1
        
        return {
            "message": "Documents embedded successfully",
            "total_chunks": len(validated_docs),
            "total_documents": len(docs_by_id),
            "chunks_per_document": dict(docs_by_id)
        }
    
    def delete_by_document_id(self, document_id: str) -> Dict[str, Any]:
        """Delete semua chunks dengan document_id tertentu"""
        try:
            # Get all chunk IDs untuk document ini
            results = self.vectorstore._collection.get(
                where={"document_id": document_id},
                include=[]
            )
            
            if not results['ids']:
                return {"message": f"No chunks found for document_id: {document_id}", "deleted": 0}
            
            # Delete
            self.vectorstore.delete(ids=results['ids'])
            
            return {
                "message": f"Deleted all chunks for document: {document_id}",
                "deleted": len(results['ids'])
            }
            
        except Exception as e:
            return {"error": str(e), "deleted": 0}
    
    def delete_by_chunk_id(self, chunk_id: str) -> Dict[str, Any]:
        """Delete single chunk"""
        try:
            self.vectorstore.delete(ids=[chunk_id])
            return {"message": f"Deleted chunk: {chunk_id}", "deleted": 1}
        except Exception as e:
            return {"error": str(e), "deleted": 0}
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get info tentang collection"""
        collection = self.vectorstore._collection
        count = collection.count()
        
        # Get sample untuk struktur metadata
        if count > 0:
            sample = collection.peek(limit=3)
            sample_meta = sample.get('metadatas', [])
        else:
            sample_meta = []
        
        # Count unique documents
        try:
            all_meta = collection.get(include=['metadatas'])
            doc_ids = set()
            for meta in all_meta.get('metadatas', []):
                if meta and 'document_id' in meta:
                    doc_ids.add(meta['document_id'])
            unique_docs = len(doc_ids)
            doc_id_list = list(doc_ids)[:20]  # Limit untuk display
        except:
            unique_docs = "unknown"
            doc_id_list = []
        
        return {
            "collection_name": collection.name,
            "total_chunks": count,
            "unique_documents": unique_docs,
            "document_ids": doc_id_list,
            "distance_function": collection.metadata.get("hnsw:space", "unknown"),
            "sample_metadata": sample_meta
        }
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_dict: Dict = None
    ) -> List[Document]:
        """
        Search dengan optional filter
        """
        search_kwargs = {"k": top_k}
        if filter_dict:
            search_kwargs["filter"] = filter_dict
        
        results = self.vectorstore.similarity_search_with_score(
            query=query,
            **search_kwargs
        )
        
        docs = []
        for doc, score in results:
            doc.metadata['similarity_score'] = 1 - (score / 2)  # Convert distance to similarity
            docs.append(doc)
        
        return docs


# ==============================
# API Router Factory
# ==============================
def create_embedding_router(
    config: Dict,
    db_dependency = None,
    prefix: str = "/api/v1/embed"
) -> APIRouter:
    """
    Create FastAPI router untuk embedding operations
    """
    
    router = APIRouter(prefix=prefix, tags=["Embedding"])
    manager = EmbeddingManager(config)
    
    @router.get("/info")
    def get_info():
        """Get vectorstore info"""
        return manager.get_collection_info()
    
    @router.get("/documents")
    def list_documents():
        """List all unique document_ids"""
        info = manager.get_collection_info()
        return {
            "total_documents": info["unique_documents"],
            "document_ids": info["document_ids"]
        }
    
    @router.delete("/document/{document_id}")
    def delete_document(document_id: str):
        """Delete all chunks for a document"""
        return manager.delete_by_document_id(document_id)
    
    @router.delete("/chunk/{chunk_id}")
    def delete_chunk(chunk_id: str):
        """Delete single chunk"""
        return manager.delete_by_chunk_id(chunk_id)
    
    @router.post("/search")
    def search_documents(
        query: str,
        top_k: int = 5,
        jenjang: str = None,
        tahun: str = None
    ):
        """Search dengan optional filters"""
        filter_dict = {}
        if jenjang:
            filter_dict["jenjang"] = jenjang
        if tahun:
            filter_dict["tahun"] = tahun
        
        results = manager.search(
            query=query,
            top_k=top_k,
            filter_dict=filter_dict if filter_dict else None
        )
        
        return {
            "query": query,
            "results": [
                {
                    "content": doc.page_content[:200] + "...",
                    "metadata": doc.metadata,
                    "similarity": doc.metadata.get('similarity_score', 0)
                }
                for doc in results
            ]
        }
    
    return router, manager


# ==============================
# Standalone Test
# ==============================
if __name__ == "__main__":
    # Test configuration
    test_config = {
        "embeddings": {
            "model": "openai",
            "openai": {
                "model_name": "text-embedding-3-small"
            }
        },
        "vectordb": {
            "chroma": {
                "collection_name": "test_collection",
                "persist_directory": "./test_chroma",
                "distance_function": "cosine"
            }
        }
    }
    
    print("Embedding Router module loaded successfully")
    print("Use: create_embedding_router(config) to create router")
