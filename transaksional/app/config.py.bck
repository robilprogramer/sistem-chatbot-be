import os
import re
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()


class ConfigLoader:
    """Load dan parse configuration files"""
    
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "config"
        self.config_dir = Path(config_dir)
        self._cache: Dict[str, Any] = {}
        
    def _substitute_env_vars(self, value: Any) -> Any:
        """Substitute ${VAR} atau ${VAR:default} dengan environment variables"""
        if isinstance(value, str):
            pattern = r'\$\{([^}:]+)(?::([^}]*))?\}'
            
            def replace(match):
                var_name = match.group(1)
                default = match.group(2) if match.group(2) is not None else ""
                return os.getenv(var_name, default)
            
            result = re.sub(pattern, replace, value)
            
            if result.lower() == 'true':
                return True
            elif result.lower() == 'false':
                return False
            
            try:
                if '.' in result:
                    return float(result)
                return int(result)
            except (ValueError, TypeError):
                pass
                
            return result
            
        elif isinstance(value, dict):
            return {k: self._substitute_env_vars(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._substitute_env_vars(item) for item in value]
        else:
            return value
    
    def load(self, filename: str, use_cache: bool = True) -> Dict[str, Any]:
        """Load configuration file"""
        if not filename.endswith('.yaml') and not filename.endswith('.yml'):
            filename = f"{filename}.yaml"
            
        cache_key = filename
        
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]
        
        filepath = self.config_dir / filename
        
        if not filepath.exists():
            raise FileNotFoundError(f"Config file not found: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        config = self._substitute_env_vars(config)
        
        if use_cache:
            self._cache[cache_key] = config
            
        return config
    
    def reload(self, filename: str = None) -> None:
        """Reload configuration (clear cache)"""
        if filename:
            cache_key = filename if filename.endswith('.yaml') else f"{filename}.yaml"
            self._cache.pop(cache_key, None)
        else:
            self._cache.clear()
    
    def get(self, filename: str, key: str, default: Any = None) -> Any:
        """Get specific key from config using dot notation"""
        config = self.load(filename)
        
        keys = key.split('.')
        value = config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
                
        return value


# Singleton instance
_config_loader: Optional[ConfigLoader] = None


def get_config_loader(config_dir: str = None) -> ConfigLoader:
    """Get singleton config loader"""
    global _config_loader
    if _config_loader is None or config_dir is not None:
        _config_loader = ConfigLoader(config_dir)
    return _config_loader


@lru_cache()
def get_app_config() -> Dict[str, Any]:
    """Get application configuration"""
    return get_config_loader().load("app_config")


@lru_cache()
def get_form_config() -> Dict[str, Any]:
    """Get form configuration"""
    return get_config_loader().load("form_config")


def reload_configs():
    """Reload all configurations"""
    get_config_loader().reload()
    get_app_config.cache_clear()
    get_form_config.cache_clear()


class Settings:
    """Quick access to settings with proper property definitions"""
    
    # ==========================================================================
    # RAW CONFIG SECTIONS
    # ==========================================================================
    
    @property
    def app(self) -> Dict[str, Any]:
        return get_app_config().get("app", {})
    
    @property
    def server(self) -> Dict[str, Any]:
        return get_app_config().get("server", {})
    
    @property
    def database(self) -> Dict[str, Any]:
        return get_app_config().get("database", {})
    
    @property
    def llm(self) -> Dict[str, Any]:
        return get_app_config().get("llm", {})
    
    @property
    def session(self) -> Dict[str, Any]:
        return get_app_config().get("session", {})
    
    @property
    def upload(self) -> Dict[str, Any]:
        return get_app_config().get("upload", {})
    
    @property
    def notifications(self) -> Dict[str, Any]:
        return get_app_config().get("notifications", {})
    
    @property
    def cors(self) -> Dict[str, Any]:
        return get_app_config().get("cors", {})
    
    @property
    def security(self) -> Dict[str, Any]:
        return get_app_config().get("security", {})
    
    @property
    def registration(self) -> Dict[str, Any]:
        return get_app_config().get("registration", {})
    
    @property
    def informational_api(self) -> Dict[str, Any]:
        return get_app_config().get("informational_api", {})
    
    # ==========================================================================
    # FORM CONFIG SECTIONS
    # ==========================================================================
    
    @property
    def form(self) -> Dict[str, Any]:
        return get_form_config().get("form", {})
    
    @property
    def steps(self) -> list:
        return get_form_config().get("steps", [])
    
    @property
    def fields(self) -> Dict[str, Any]:
        return get_form_config().get("fields", {})
    
    @property
    def messages(self) -> Dict[str, Any]:
        return get_form_config().get("messages", {})
    
    @property
    def commands(self) -> Dict[str, Any]:
        return get_form_config().get("commands", {})
    
    # ==========================================================================
    # COMMON SHORTCUTS - APP
    # ==========================================================================
    
    @property
    def debug(self) -> bool:
        return self.app.get("debug", False)
    
    @property
    def app_name(self) -> str:
        return self.app.get("name", "YPI Al-Azhar Chatbot")
    
    @property
    def app_version(self) -> str:
        return self.app.get("version", "1.0.0")
    
    # ==========================================================================
    # COMMON SHORTCUTS - SERVER & API PREFIXES
    # ==========================================================================
    
    @property
    def host(self) -> str:
        return self.server.get("host", "0.0.0.0")
    
    @property
    def port(self) -> int:
        return self.server.get("port", 8000)
    
    @property
    def informational_prefix(self) -> str:
        """API prefix untuk informational chatbot (RAG)"""
        return self.server.get("informational_prefix", "/api/informational/v1")

    @property
    def transactional_prefix(self) -> str:
        """API prefix untuk transactional chatbot (pendaftaran)"""
        return self.server.get("transactional_prefix", "/api/transactional/v1")
    
    # Alias untuk backward compatibility
    # @property
    # def api_prefix(self) -> str:
    #     """Alias untuk transactional_prefix (backward compatibility)"""
    #     return self.transactional_prefix
    
    # ==========================================================================
    # COMMON SHORTCUTS - DATABASE
    # ==========================================================================
    
    @property
    def database_url(self) -> str:
        return self.database.get("url", "")
    
    @property
    def database_pool_size(self) -> int:
        return self.database.get("pool_size", 5)
    
    # ==========================================================================
    # COMMON SHORTCUTS - LLM
    # ==========================================================================
    
    @property
    def llm_provider(self) -> str:
        return self.llm.get("provider", "openai")
    
    @property
    def openai_api_key(self) -> str:
        return self.llm.get("openai", {}).get("api_key", "")
    
    @property
    def openai_model(self) -> str:
        return self.llm.get("openai", {}).get("model", "gpt-4o-mini")
    
    @property
    def openai_temperature(self) -> float:
        return self.llm.get("openai", {}).get("temperature", 0.7)
    
    @property
    def openai_max_tokens(self) -> int:
        return self.llm.get("openai", {}).get("max_tokens", 500)
    
    @property
    def anthropic_api_key(self) -> str:
        return self.llm.get("anthropic", {}).get("api_key", "")
    
    @property
    def anthropic_model(self) -> str:
        return self.llm.get("anthropic", {}).get("model", "claude-3-sonnet-20240229")
    
    # ==========================================================================
    # COMMON SHORTCUTS - SESSION
    # ==========================================================================
    
    @property
    def session_timeout(self) -> int:
        return self.session.get("timeout_seconds", 3600)
    
    @property
    def max_conversation_history(self) -> int:
        return self.session.get("max_conversation_history", 20)
    
    # ==========================================================================
    # COMMON SHORTCUTS - UPLOAD
    # ==========================================================================
    
    @property
    def upload_directory(self) -> str:
        return self.upload.get("directory", "./uploads")
    
    @property
    def max_file_size_mb(self) -> int:
        return self.upload.get("max_file_size_mb", 5)
    
    @property
    def allowed_extensions(self) -> list:
        return self.upload.get("allowed_extensions", [".pdf", ".jpg", ".jpeg", ".png"])
    
    # ==========================================================================
    # COMMON SHORTCUTS - SECURITY
    # ==========================================================================
    
    @property
    def secret_key(self) -> str:
        return self.security.get("secret_key", "change-this-in-production")
    
    # ==========================================================================
    # COMMON SHORTCUTS - INFORMATIONAL API
    # ==========================================================================
    
    @property
    def informational_api_enabled(self) -> bool:
        return self.informational_api.get("enabled", True)
    
    @property
    def informational_api_base_url(self) -> str:
        return self.informational_api.get("base_url", "http://localhost:8080/api/v1")
    
    @property
    def informational_api_timeout(self) -> int:
        return self.informational_api.get("timeout", 30)


# Global settings instance
settings = Settings()


if __name__ == "__main__":
    print("=== Testing Config Loader ===\n")
    
    loader = get_config_loader()
    
    print("App Config:")
    app_config = loader.load("app_config")
    print(f"  App Name: {app_config.get('app', {}).get('name')}")
    print(f"  Debug: {app_config.get('app', {}).get('debug')}")
    print(f"  Database URL: {app_config.get('database', {}).get('url')}")
    
    print("\nForm Config:")
    try:
        form_config = loader.load("form_config")
        print(f"  Form ID: {form_config.get('form', {}).get('id')}")
        print(f"  Steps: {[s['id'] for s in form_config.get('steps', [])]}")
    except FileNotFoundError:
        print("  (form_config.yaml not found - skipping)")
    
    print("\nSettings shortcuts:")
    print(f"  settings.debug: {settings.debug}")
    print(f"  settings.informational_prefix: {settings.informational_prefix}")
    print(f"  settings.transactional_prefix: {settings.transactional_prefix}")
    # print(f"  settings.api_prefix: {settings.api_prefix}")
    print(f"  settings.llm_provider: {settings.llm_provider}")
    print(f"  settings.database_url: {settings.database_url}")