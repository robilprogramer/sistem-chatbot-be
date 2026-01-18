"""
Config Loader - Load dan parse config.yaml

Features:
1. Load YAML config dengan environment variable resolution
2. Singleton pattern untuk konsistensi
3. Easy access ke semua config sections
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from functools import lru_cache


class ConfigLoader:
    """
    Centralized Configuration Loader
    
    Usage:
        config = get_config()
        embedding_cfg = config.get_embeddings()
        prompts = config.get_prompts()
    """
    
    def __init__(self, config_path: str = None):
        """
        Initialize ConfigLoader
        
        Args:
            config_path: Path ke config.yaml
        """
        self._config_path = self._resolve_config_path(config_path)
        self._config = self._load_config()
        
        print(f"📋 Config loaded from: {self._config_path}")
    
    def _resolve_config_path(self, config_path: str = None) -> str:
        """Resolve config path"""
        if config_path and Path(config_path).exists():
            return config_path
        
        # Try default paths
        default_paths = [
            "informasional/config/config.yaml",
            "config/config.yaml",
            "../config/config.yaml",
            "config.yaml"
        ]
        
        for path in default_paths:
            if Path(path).exists():
                return path
        
        raise FileNotFoundError(
            f"Config file not found. Tried: {default_paths}"
        )
    
    def _load_config(self) -> Dict[str, Any]:
        """Load and parse YAML config"""
        with open(self._config_path, "r", encoding="utf-8") as f:
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
    
    # =========================================================================
    # CONFIG ACCESSORS
    # =========================================================================
    
    @property
    def raw(self) -> Dict[str, Any]:
        """Get raw config dict"""
        return self._config
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by key"""
        return self._config.get(key, default)
    
    def get_app(self) -> Dict[str, Any]:
        """Get app config"""
        return self._config.get("app", {})
    
    def get_chunking(self) -> Dict[str, Any]:
        """Get chunking config"""
        return self._config.get("chunking", {})
    
    def get_embeddings(self) -> Dict[str, Any]:
        """Get embeddings config"""
        return self._config.get("embeddings", {})
    
    def get_vectordb(self) -> Dict[str, Any]:
        """Get vectordb config"""
        return self._config.get("vectordb", {})
    
    def get_chroma(self) -> Dict[str, Any]:
        """Get ChromaDB config"""
        return self.get_vectordb().get("chroma", {})
    
    def get_retrieval(self) -> Dict[str, Any]:
        """Get retrieval config"""
        defaults = {
            "top_k": 10,
            "similarity_threshold": 0.4,
            "max_documents": 3,
            "fetch_full_document": True
        }
        cfg = self._config.get("retrieval", {})
        return {**defaults, **cfg}
    
    def get_llm(self) -> Dict[str, Any]:
        """Get LLM config"""
        return self._config.get("llm", {})
    
    def get_prompts(self) -> Dict[str, Any]:
        """Get all prompts config"""
        return self._config.get("prompts", {})
    
    def get_informational_prompts(self) -> Dict[str, str]:
        """Get informational mode prompts"""
        prompts = self.get_prompts().get("informational", {})
        
        # Defaults
        defaults = {
            "system_prompt": "Anda adalah asisten virtual YPI Al-Azhar.",
            "query_prompt": "Pertanyaan: {question}\n\nKonteks:\n{context}\n\nJawaban:",
            "no_context_response": "Maaf, informasi tidak ditemukan.",
            "low_relevance_response": "Maaf, relevansi informasi rendah."
        }
        
        return {**defaults, **prompts}
    
    def get_system_prompt(self) -> str:
        """Get system prompt for informational mode"""
        return self.get_informational_prompts().get("system_prompt", "")
    
    def get_query_prompt(self) -> str:
        """Get query prompt template"""
        return self.get_informational_prompts().get("query_prompt", "")
    
    def get_no_context_response(self) -> str:
        """Get response when no context found"""
        return self.get_informational_prompts().get("no_context_response", "")
    
    def get_low_relevance_response(self) -> str:
        """Get response when relevance is low"""
        return self.get_informational_prompts().get("low_relevance_response", "")


# =============================================================================
# SINGLETON PATTERN
# =============================================================================

_config_instance: Optional[ConfigLoader] = None


def get_config(config_path: str = None) -> ConfigLoader:
    """
    Get singleton ConfigLoader instance
    
    Args:
        config_path: Path ke config.yaml (required on first call)
    
    Returns:
        ConfigLoader singleton instance
    """
    global _config_instance
    
    if _config_instance is None:
        _config_instance = ConfigLoader(config_path=config_path)
    
    return _config_instance


def reset_config():
    """Reset config singleton"""
    global _config_instance
    _config_instance = None
    print("🔄 Config reset")


# =============================================================================
# BACKWARD COMPATIBILITY - APP_CONFIG dict
# =============================================================================

def get_app_config() -> Dict[str, Any]:
    """
    Get raw config dict (backward compatibility)
    
    Usage:
        from informasional.core.config_loader import APP_CONFIG
        embedding_cfg = APP_CONFIG["embeddings"]
    """
    return get_config().raw


# Lazy-loaded APP_CONFIG for backward compatibility
class _AppConfigProxy:
    """Proxy class untuk lazy loading APP_CONFIG"""
    
    def __getitem__(self, key):
        return get_config().raw[key]
    
    def __contains__(self, key):
        return key in get_config().raw
    
    def get(self, key, default=None):
        return get_config().raw.get(key, default)


APP_CONFIG = _AppConfigProxy()