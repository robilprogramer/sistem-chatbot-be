"""
Embedding Manager - Centralized embedding configuration

Features:
1. Load config dari YAML file
2. Singleton pattern - sama instance untuk embed & retrieval
3. Support OpenAI & HuggingFace embeddings
4. Consistent dengan ChromaDB vectorstore
"""

import os
import time
import yaml
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional
from functools import lru_cache

from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.embeddings import Embeddings


class EmbeddingProvider(Enum):
    """Supported embedding providers"""
    OPENAI = "openai"
    HUGGINGFACE = "huggingface"


class EmbeddingConfig:
    """
    Configuration loader untuk Embeddings
    Load dari YAML file untuk konsistensi
    """
    
    def __init__(self, config_path: str = None, config_dict: Dict = None):
        if config_dict:
            self._config = config_dict
        elif config_path:
            self._config = self._load_yaml(config_path)
        else:
            raise ValueError("Either config_path or config_dict must be provided")
        
        self._embedding_cfg = self._config.get("embeddings", {})
        self._vectordb_cfg = self._config.get("vectordb", {})
    
    def _load_yaml(self, path: str) -> Dict[str, Any]:
        """Load YAML config file with environment variable resolution"""
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        return self._resolve_env_vars(config)
    
    def _resolve_env_vars(self, d: Any) -> Any:
        """Resolve ${VAR} patterns to environment variables"""
        if isinstance(d, dict):
            return {k: self._resolve_env_vars(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [self._resolve_env_vars(v) for v in d]
        elif isinstance(d, str) and d.startswith("${") and d.endswith("}"):
            var_name = d[2:-1]
            return os.getenv(var_name, "")
        return d
    
    @property
    def provider(self) -> str:
        """Get embedding provider: openai or huggingface"""
        return self._embedding_cfg.get("provider",self._embedding_cfg.get("model", "openai"))
    
    @property
    def openai_config(self) -> Dict[str, Any]:
        """Get OpenAI embedding config"""
        defaults = {
            "model_name": "text-embedding-3-small",
            "dimensions": 1536
        }
        cfg = self._embedding_cfg.get("openai", {})
        return {**defaults, **cfg}
    
    @property
    def huggingface_config(self) -> Dict[str, Any]:
        """Get HuggingFace embedding config"""
        defaults = {
            "model_name": "sentence-transformers/all-MiniLM-L6-v2",
            "dimensions": 384,
            "device": "cpu"
        }
        cfg = self._embedding_cfg.get("huggingface", {})
        return {**defaults, **cfg}
    
    @property
    def chroma_config(self) -> Dict[str, Any]:
        """Get ChromaDB config"""
        defaults = {
            "collection_name": "ypi_knowledge_base",
            "persist_directory": "data/chroma_db",
            "distance_function": "cosine"
        }
        cfg = self._vectordb_cfg.get("chroma", {})
        return {**defaults, **cfg}
    
    def get_full_config(self) -> Dict[str, Any]:
        """Get full embedding & vectordb configuration"""
        return {
            "provider": self.provider,
            "openai": self.openai_config,
            "huggingface": self.huggingface_config,
            "chroma": self.chroma_config
        }


class EmbeddingManager:
    """
    Centralized Embedding Manager
    
    PENTING: Gunakan get_embedding_manager() untuk mendapatkan singleton instance.
    Ini memastikan embedding yang sama digunakan untuk:
    - Embedding chunks
    - Retrieval queries
    - Vector similarity search
    
    Usage:
        manager = get_embedding_manager("config/config.yaml")
        embeddings = manager.get_embeddings()  # LangChain Embeddings object
        vectors = manager.embed_documents(texts)
    """
    
    def __init__(self, config_path: str = None, config: Dict = None):
        """
        Initialize EmbeddingManager
        
        Args:
            config_path: Path ke file YAML config
            config: Dictionary config (alternatif dari YAML)
        """
        # Load configuration
        self._cfg = EmbeddingConfig(config_path=config_path, config_dict=config)
        
        # Determine provider
        provider_str = self._cfg.provider.lower()
        if provider_str == "openai":
            self._provider = EmbeddingProvider.OPENAI
        elif provider_str == "huggingface":
            self._provider = EmbeddingProvider.HUGGINGFACE
        else:
            raise ValueError(f"Unsupported embedding provider: {provider_str}")
        
        # Initialize embeddings
        self._embeddings = self._initialize_embeddings()
        self._model_name = self._get_model_name()
        
        # Log configuration
        self._log_config()
    
    def _get_model_name(self) -> str:
        """Get current model name"""
        if self._provider == EmbeddingProvider.OPENAI:
            return self._cfg.openai_config["model_name"]
        else:
            return self._cfg.huggingface_config["model_name"]
    
    def _log_config(self):
        """Log current configuration"""
        print(f"🔤 EmbeddingManager initialized")
        print(f"   └─ Provider: {self._provider.value}")
        print(f"   └─ Model: {self._model_name}")
        print(f"   └─ Dimensions: {self.get_dimension()}")
    
    def _initialize_embeddings(self) -> Embeddings:
        """Initialize embedding model based on provider"""
        
        if self._provider == EmbeddingProvider.OPENAI:
            cfg = self._cfg.openai_config
            
            # Check API key
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            
            return OpenAIEmbeddings(
                model=cfg["model_name"],
                dimensions=cfg.get("dimensions"),
                openai_api_key=api_key
            )
        
        elif self._provider == EmbeddingProvider.HUGGINGFACE:
            cfg = self._cfg.huggingface_config
            
            # Check CUDA availability
            device = cfg.get("device", "cpu")
            if device == "cuda":
                try:
                    import torch
                    if not torch.cuda.is_available():
                        print("   ⚠️ CUDA not available, falling back to CPU")
                        device = "cpu"
                except ImportError:
                    device = "cpu"
            
            return HuggingFaceEmbeddings(
                model_name=cfg["model_name"],
                model_kwargs={"device": device},
                encode_kwargs={"normalize_embeddings": True}
            )
        
        else:
            raise ValueError(f"Unsupported provider: {self._provider}")
    
    # =========================================================================
    # PUBLIC METHODS
    # =========================================================================
    
    @property
    def provider(self) -> EmbeddingProvider:
        """Get current embedding provider"""
        return self._provider
    
    @property
    def model_name(self) -> str:
        """Get current model name"""
        return self._model_name
    
    @property
    def config(self) -> Dict[str, Any]:
        """Get full configuration"""
        return self._cfg.get_full_config()
    
    def get_embeddings(self) -> Embeddings:
        """
        Get LangChain Embeddings object
        
        Use this for:
        - ChromaDB initialization
        - LangChain retrievers
        - Direct embedding operations
        """
        return self._embeddings
    
    def get_dimension(self) -> int:
        """Get embedding dimension"""
        if self._provider == EmbeddingProvider.OPENAI:
            return self._cfg.openai_config.get("dimensions", 1536)
        elif self._provider == EmbeddingProvider.HUGGINGFACE:
            return self._cfg.huggingface_config.get("dimensions", 384)
        return 0
    
    def get_chroma_config(self) -> Dict[str, Any]:
        """Get ChromaDB configuration"""
        return self._cfg.chroma_config
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple documents
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        print(f"📊 Embedding {len(texts)} documents...")
        start_time = time.time()
        
        vectors = self._embeddings.embed_documents(texts)
        
        elapsed = time.time() - start_time
        print(f"✅ Embedded in {elapsed:.2f}s ({len(texts)/elapsed:.1f} docs/s)")
        
        return vectors
    
    def embed_query(self, text: str) -> List[float]:
        """
        Embed a single query
        
        Args:
            text: Query text
            
        Returns:
            Embedding vector
        """
        return self._embeddings.embed_query(text)
    
    def get_info(self) -> Dict[str, Any]:
        """Get embedding manager info"""
        return {
            "provider": self._provider.value,
            "model_name": self._model_name,
            "dimension": self.get_dimension(),
            "chroma_collection": self._cfg.chroma_config["collection_name"],
            "chroma_persist_dir": self._cfg.chroma_config["persist_directory"]
        }


# =============================================================================
# SINGLETON PATTERN - IMPORTANT FOR CONSISTENCY
# =============================================================================

# Global instance holder
_embedding_manager_instance: Optional[EmbeddingManager] = None
_config_path_used: Optional[str] = None


def get_embedding_manager(config_path: str = None) -> EmbeddingManager:
    """
    Get singleton EmbeddingManager instance
    
    PENTING: Selalu gunakan fungsi ini untuk mendapatkan EmbeddingManager.
    Ini memastikan embedding yang SAMA digunakan untuk:
    - Embedding router (embed chunks)
    - Retrieval router (search queries)
    - Chat service (RAG)
    
    Args:
        config_path: Path ke config.yaml (required on first call)
    
    Returns:
        EmbeddingManager singleton instance
    
    Example:
        # Di embedding_router.py
        manager = get_embedding_manager("config/config.yaml")
        
        # Di retrieval_router.py
        manager = get_embedding_manager()  # Reuse same instance
    """
    global _embedding_manager_instance, _config_path_used
    
    # First call - must provide config_path
    if _embedding_manager_instance is None:
        if config_path is None:
            # Try default path
            default_paths = [
                "informasional/config/config.yaml",
                "config/config.yaml",
                "../config/config.yaml"
            ]
            for path in default_paths:
                if Path(path).exists():
                    config_path = path
                    break
            
            if config_path is None:
                raise ValueError(
                    "config_path required on first call to get_embedding_manager()"
                )
        
        print(f"🔧 Initializing EmbeddingManager from: {config_path}")
        _embedding_manager_instance = EmbeddingManager(config_path=config_path)
        _config_path_used = config_path
    
    return _embedding_manager_instance


def reset_embedding_manager():
    """
    Reset singleton instance
    
    Use this for:
    - Testing
    - Config changes
    - Re-initialization
    """
    global _embedding_manager_instance, _config_path_used
    _embedding_manager_instance = None
    _config_path_used = None
    print("🔄 EmbeddingManager reset")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def sanitize_metadata_for_chroma(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize metadata untuk ChromaDB compatibility
    
    ChromaDB hanya support: str, int, float, bool
    None, list, dict harus diconvert
    """
    if metadata is None:
        return {}
    
    safe = {}
    for key, value in metadata.items():
        if value is None:
            safe[key] = ""
        elif isinstance(value, bool):
            safe[key] = value
        elif isinstance(value, (int, float)):
            safe[key] = value
        elif isinstance(value, str):
            safe[key] = value
        elif isinstance(value, list):
            # Convert list to comma-separated string
            safe[key] = ", ".join(str(item) for item in value)
        elif isinstance(value, dict):
            # Convert dict to string
            safe[key] = str(value)
        else:
            safe[key] = str(value)
    
    return safe