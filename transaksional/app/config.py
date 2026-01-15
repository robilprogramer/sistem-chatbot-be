
import os
import re
import yaml
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from functools import lru_cache
from datetime import datetime, timedelta
from enum import Enum
from dotenv import load_dotenv
from contextlib import contextmanager
import threading

load_dotenv()


# =============================================================================
# ENUMS
# =============================================================================

class ConfigSource(str, Enum):
    YAML = "yaml"
    DATABASE = "database"


# =============================================================================
# YAML CONFIG PROVIDER
# =============================================================================

class YAMLConfigProvider:
    """Load config from YAML files"""
    
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "config"
        self.config_dir = Path(config_dir)
        self._cache: Dict[str, Any] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=5)
        self._lock = threading.Lock()
    
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
    
    def _is_cache_valid(self, key: str) -> bool:
        if key not in self._cache_time:
            return False
        return datetime.now() - self._cache_time[key] < self._cache_ttl
    
    def load(self, filename: str, use_cache: bool = True) -> Dict[str, Any]:
        """Load configuration file"""
        if not filename.endswith('.yaml') and not filename.endswith('.yml'):
            filename = f"{filename}.yaml"
        
        cache_key = filename
        
        with self._lock:
            if use_cache and cache_key in self._cache and self._is_cache_valid(cache_key):
                return self._cache[cache_key]
        
        filepath = self.config_dir / filename
        
        if not filepath.exists():
            raise FileNotFoundError(f"Config file not found: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        config = self._substitute_env_vars(config)
        
        if use_cache:
            with self._lock:
                self._cache[cache_key] = config
                self._cache_time[cache_key] = datetime.now()
            
        return config
    
    def load_form_config(self) -> Dict[str, Any]:
        return self.load("form_config").get("form", {})
    
    def load_steps(self) -> List[Dict[str, Any]]:
        return self.load("form_config").get("steps", [])
    
    def load_fields(self) -> Dict[str, Dict[str, Any]]:
        return self.load("form_config").get("fields", {})
    
    def load_messages(self) -> Dict[str, Any]:
        return self.load("form_config").get("messages", {})
    
    def load_commands(self) -> Dict[str, Any]:
        return self.load("form_config").get("commands", {})
    
    def load_full_config(self) -> Dict[str, Any]:
        return self.load("form_config")
    
    def reload(self):
        """Clear cache to force reload"""
        with self._lock:
            self._cache.clear()
            self._cache_time.clear()
    
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


# =============================================================================
# DATABASE CONFIG PROVIDER
# =============================================================================

class DatabaseConfigProvider:
    """Load config from PostgreSQL database"""
    
    def __init__(self, database_url: str = None):
        self.database_url = database_url or os.getenv("DATABASE_URL")
        self._pool = None
        self._cache: Dict[str, Any] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=2)  # Shorter TTL for DB
        self._lock = threading.Lock()
        self._initialized = False
    
    def _get_pool(self):
        """Lazy initialization of connection pool"""
        if self._pool is None:
            try:
                import psycopg2
                import psycopg2.pool
                from psycopg2.extras import RealDictCursor
                
                self._pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=5,
                    dsn=self.database_url,
                    cursor_factory=RealDictCursor
                )
                self._initialized = True
                print(f"✅ Database config provider initialized")
            except Exception as e:
                print(f"❌ Failed to initialize database config provider: {e}")
                raise
        return self._pool
    
    @contextmanager
    def _get_connection(self):
        """Get connection from pool"""
        pool = self._get_pool()
        conn = pool.getconn()
        try:
            yield conn
        finally:
            pool.putconn(conn)
    
    def _is_cache_valid(self, key: str) -> bool:
        if key not in self._cache_time:
            return False
        return datetime.now() - self._cache_time[key] < self._cache_ttl
    
    def _get_active_config_id(self) -> Optional[int]:
        """Get currently active form config ID"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id FROM form_configs 
                    WHERE is_active = true 
                    ORDER BY updated_at DESC LIMIT 1
                """)
                result = cursor.fetchone()
                return result['id'] if result else None
        except Exception as e:
            print(f"⚠️ Error getting active config ID: {e}")
            return None
    
    def load_form_config(self) -> Dict[str, Any]:
        """Load form config section from database"""
        cache_key = "form_config"
        
        with self._lock:
            if cache_key in self._cache and self._is_cache_valid(cache_key):
                return self._cache[cache_key]
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT config_data FROM form_configs 
                    WHERE is_active = true 
                    ORDER BY updated_at DESC LIMIT 1
                """)
                result = cursor.fetchone()
                
                if result:
                    config = result['config_data']
                    if isinstance(config, str):
                        config = json.loads(config)
                    form_config = config.get("form", config)
                    
                    with self._lock:
                        self._cache[cache_key] = form_config
                        self._cache_time[cache_key] = datetime.now()
                    
                    return form_config
        except Exception as e:
            print(f"⚠️ Error loading form config from DB: {e}")
        
        return {}
    
    def load_steps(self) -> List[Dict[str, Any]]:
        """Load steps from database"""
        cache_key = "steps"
        
        with self._lock:
            if cache_key in self._cache and self._is_cache_valid(cache_key):
                return self._cache[cache_key]
        
        config_id = self._get_active_config_id()
        if not config_id:
            return []
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT step_id, step_name, description, step_order, 
                           is_mandatory, can_skip, skip_conditions, icon
                    FROM form_steps 
                    WHERE config_id = %s AND is_active = true
                    ORDER BY step_order
                """, (config_id,))
                results = cursor.fetchall()
                
                steps = []
                for row in results:
                    skip_conditions = row.get("skip_conditions")
                    if isinstance(skip_conditions, str):
                        try:
                            skip_conditions = json.loads(skip_conditions)
                        except:
                            skip_conditions = []
                    
                    steps.append({
                        "id": row["step_id"],
                        "name": row["step_name"],
                        "description": row.get("description", ""),
                        "order": row["step_order"],
                        "is_mandatory": row.get("is_mandatory", True),
                        "can_skip": row.get("can_skip", False),
                        "skip_conditions": skip_conditions or [],
                        "icon": row.get("icon")
                    })
                
                with self._lock:
                    self._cache[cache_key] = steps
                    self._cache_time[cache_key] = datetime.now()
                
                print(f"📋 Loaded {len(steps)} steps from database")
                return steps
                
        except Exception as e:
            print(f"⚠️ Error loading steps from DB: {e}")
            return []
    
    def load_fields(self) -> Dict[str, Dict[str, Any]]:
        """Load fields from database"""
        cache_key = "fields"
        
        with self._lock:
            if cache_key in self._cache and self._is_cache_valid(cache_key):
                return self._cache[cache_key]
        
        config_id = self._get_active_config_id()
        if not config_id:
            return {}
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT field_id, step_id, field_label, field_type, is_mandatory,
                           validation, options, examples, tips, extract_keywords,
                           auto_formats, auto_clean, default_value, field_order
                    FROM form_fields 
                    WHERE config_id = %s AND is_active = true
                    ORDER BY field_order
                """, (config_id,))
                results = cursor.fetchall()
                
                fields = {}
                for row in results:
                    field_id = row["field_id"]
                    
                    # Parse JSON fields
                    validation = row.get("validation")
                    if isinstance(validation, str):
                        try:
                            validation = json.loads(validation)
                        except:
                            validation = {}
                    
                    options = row.get("options")
                    if isinstance(options, str):
                        try:
                            options = json.loads(options)
                        except:
                            options = []
                    
                    examples = row.get("examples")
                    if isinstance(examples, str):
                        try:
                            examples = json.loads(examples)
                        except:
                            examples = []
                    
                    extract_keywords = row.get("extract_keywords")
                    if isinstance(extract_keywords, str):
                        try:
                            extract_keywords = json.loads(extract_keywords)
                        except:
                            extract_keywords = []
                    
                    auto_formats = row.get("auto_formats")
                    if isinstance(auto_formats, str):
                        try:
                            auto_formats = json.loads(auto_formats)
                        except:
                            auto_formats = []
                    
                    fields[field_id] = {
                        "label": row["field_label"],
                        "step": row["step_id"],
                        "type": row["field_type"],
                        "is_mandatory": row.get("is_mandatory", False),
                        "validation": validation or {},
                        "options": options or [],
                        "examples": examples or [],
                        "tips": row.get("tips", ""),
                        "extract_keywords": extract_keywords or [],
                        "auto_formats": auto_formats or [],
                        "auto_clean": row.get("auto_clean", False),
                        "default": row.get("default_value")
                    }
                
                with self._lock:
                    self._cache[cache_key] = fields
                    self._cache_time[cache_key] = datetime.now()
                
                print(f"📋 Loaded {len(fields)} fields from database")
                return fields
                
        except Exception as e:
            print(f"⚠️ Error loading fields from DB: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def load_messages(self) -> Dict[str, Any]:
        """Load messages from database"""
        cache_key = "messages"
        
        with self._lock:
            if cache_key in self._cache and self._is_cache_valid(cache_key):
                return self._cache[cache_key]
        
        config_id = self._get_active_config_id()
        if not config_id:
            return {}
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT message_key, message_template
                    FROM form_messages 
                    WHERE config_id = %s AND is_active = true
                """, (config_id,))
                results = cursor.fetchall()
                
                # Convert flat keys to nested dict
                messages = {}
                for row in results:
                    keys = row["message_key"].split(".")
                    current = messages
                    for key in keys[:-1]:
                        if key not in current:
                            current[key] = {}
                        current = current[key]
                    current[keys[-1]] = row["message_template"]
                
                with self._lock:
                    self._cache[cache_key] = messages
                    self._cache_time[cache_key] = datetime.now()
                
                return messages
                
        except Exception as e:
            print(f"⚠️ Error loading messages from DB: {e}")
            return {}
    
    def load_commands(self) -> Dict[str, Any]:
        """Load commands from database"""
        cache_key = "commands"
        
        with self._lock:
            if cache_key in self._cache and self._is_cache_valid(cache_key):
                return self._cache[cache_key]
        
        config_id = self._get_active_config_id()
        if not config_id:
            return {}
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT command_name, keywords, pattern
                    FROM form_commands 
                    WHERE config_id = %s AND is_active = true
                """, (config_id,))
                results = cursor.fetchall()
                
                commands = {}
                for row in results:
                    keywords = row.get("keywords")
                    if isinstance(keywords, str):
                        try:
                            keywords = json.loads(keywords)
                        except:
                            keywords = []
                    
                    commands[row["command_name"]] = {
                        "keywords": keywords or [],
                        "pattern": row.get("pattern")
                    }
                
                with self._lock:
                    self._cache[cache_key] = commands
                    self._cache_time[cache_key] = datetime.now()
                
                return commands
                
        except Exception as e:
            print(f"⚠️ Error loading commands from DB: {e}")
            return {}
    
    def load_full_config(self) -> Dict[str, Any]:
        """Load complete config from database"""
        return {
            "form": self.load_form_config(),
            "steps": self.load_steps(),
            "fields": self.load_fields(),
            "messages": self.load_messages(),
            "commands": self.load_commands()
        }
    
    def reload(self):
        """Clear cache to force reload"""
        with self._lock:
            self._cache.clear()
            self._cache_time.clear()
        print("🔄 Database config cache cleared")


# =============================================================================
# DYNAMIC CONFIG LOADER (Main Entry Point)
# =============================================================================

class DynamicConfigLoader:
    """
    Main config loader that switches between YAML and Database.
    Reads FORM_CONFIG_SOURCE from environment.
    """
    
    def __init__(self):
        # Read source from environment
        source_str = os.getenv("FORM_CONFIG_SOURCE", "yaml").lower()
        fallback_str = os.getenv("FORM_CONFIG_FALLBACK", "yaml").lower()
        
        self.source = ConfigSource(source_str) if source_str in ["yaml", "database"] else ConfigSource.YAML
        self.fallback = ConfigSource(fallback_str) if fallback_str in ["yaml", "database"] else ConfigSource.YAML
        
        print(f"📋 Config source: {self.source.value}, fallback: {self.fallback.value}")
        
        # Initialize providers
        self._yaml_provider = YAMLConfigProvider()
        self._db_provider = None
        
        # Lazy init database provider only if needed
        if self.source == ConfigSource.DATABASE or self.fallback == ConfigSource.DATABASE:
            try:
                self._db_provider = DatabaseConfigProvider()
            except Exception as e:
                print(f"⚠️ Could not initialize database provider: {e}")
                if self.source == ConfigSource.DATABASE:
                    print(f"⚠️ Falling back to YAML")
                    self.source = ConfigSource.YAML
    
    @property
    def provider(self):
        """Get current active provider"""
        if self.source == ConfigSource.DATABASE and self._db_provider:
            return self._db_provider
        return self._yaml_provider
    
    @property
    def fallback_provider(self):
        """Get fallback provider"""
        if self.fallback == ConfigSource.DATABASE and self._db_provider:
            return self._db_provider
        return self._yaml_provider
    
    def _try_with_fallback(self, method_name: str, *args, **kwargs):
        """Try primary source, fallback if fails"""
        try:
            method = getattr(self.provider, method_name)
            result = method(*args, **kwargs)
            
            # Check if result is empty and we have a different fallback
            if not result and self.source != self.fallback:
                print(f"⚠️ Empty result from {self.source.value}, trying fallback...")
                method = getattr(self.fallback_provider, method_name)
                return method(*args, **kwargs)
            
            return result
            
        except Exception as e:
            print(f"⚠️ Primary source failed ({method_name}): {e}")
            if self.fallback != self.source:
                try:
                    print(f"   Trying fallback ({self.fallback.value})...")
                    method = getattr(self.fallback_provider, method_name)
                    return method(*args, **kwargs)
                except Exception as e2:
                    print(f"❌ Fallback also failed: {e2}")
            raise
    
    def load_form_config(self) -> Dict[str, Any]:
        return self._try_with_fallback("load_form_config")
    
    def load_steps(self) -> List[Dict[str, Any]]:
        return self._try_with_fallback("load_steps")
    
    def load_fields(self) -> Dict[str, Dict[str, Any]]:
        return self._try_with_fallback("load_fields")
    
    def load_messages(self) -> Dict[str, Any]:
        return self._try_with_fallback("load_messages")
    
    def load_commands(self) -> Dict[str, Any]:
        return self._try_with_fallback("load_commands")
    
    def load_full_config(self) -> Dict[str, Any]:
        """Load complete config"""
        return {
            "form": self.load_form_config(),
            "steps": self.load_steps(),
            "fields": self.load_fields(),
            "messages": self.load_messages(),
            "commands": self.load_commands()
        }
    
    def switch_source(self, new_source: ConfigSource):
        """Switch config source at runtime"""
        old_source = self.source
        self.source = new_source
        self.reload()
        print(f"🔄 Switched config source: {old_source.value} → {new_source.value}")
    
    def reload(self):
        """Reload all providers"""
        self._yaml_provider.reload()
        if self._db_provider:
            self._db_provider.reload()
        print("🔄 Config reloaded")


# =============================================================================
# SINGLETON & HELPER FUNCTIONS
# =============================================================================

_config_loader: Optional[DynamicConfigLoader] = None
_yaml_loader: Optional[YAMLConfigProvider] = None


def get_config_loader() -> DynamicConfigLoader:
    """Get singleton dynamic config loader"""
    global _config_loader
    if _config_loader is None:
        _config_loader = DynamicConfigLoader()
    return _config_loader


def get_yaml_loader() -> YAMLConfigProvider:
    """Get YAML loader for app_config (always YAML)"""
    global _yaml_loader
    if _yaml_loader is None:
        _yaml_loader = YAMLConfigProvider()
    return _yaml_loader


def get_app_config() -> Dict[str, Any]:
    """Get application configuration (always from YAML)"""
    return get_yaml_loader().load("app_config")


def get_form_config() -> Dict[str, Any]:
    """Get form configuration (from DB or YAML based on setting)"""
    return get_config_loader().load_full_config()


def reload_configs():
    """Reload all configurations"""
    global _config_loader, _yaml_loader
    if _yaml_loader:
        _yaml_loader.reload()
    if _config_loader:
        _config_loader.reload()


# =============================================================================
# SETTINGS CLASS (Backward Compatible)
# =============================================================================

class Settings:
    """Quick access to settings - backward compatible with existing code"""
    
    def __init__(self):
        self._app_config = None
    
    def _get_app_config(self) -> Dict[str, Any]:
        if self._app_config is None:
            self._app_config = get_app_config()
        return self._app_config
    
    @property
    def config_loader(self) -> DynamicConfigLoader:
        return get_config_loader()
    
    # ==========================================================================
    # RAW CONFIG SECTIONS - APP (Always YAML)
    # ==========================================================================
    
    @property
    def app(self) -> Dict[str, Any]:
        return self._get_app_config().get("app", {})
    
    @property
    def server(self) -> Dict[str, Any]:
        return self._get_app_config().get("server", {})
    
    @property
    def database(self) -> Dict[str, Any]:
        return self._get_app_config().get("database", {})
    
    @property
    def llm(self) -> Dict[str, Any]:
        return self._get_app_config().get("llm", {})
    
    @property
    def session(self) -> Dict[str, Any]:
        return self._get_app_config().get("session", {})
    
    @property
    def upload(self) -> Dict[str, Any]:
        return self._get_app_config().get("upload", {})
    
    @property
    def notifications(self) -> Dict[str, Any]:
        return self._get_app_config().get("notifications", {})
    
    @property
    def cors(self) -> Dict[str, Any]:
        return self._get_app_config().get("cors", {})
    
    @property
    def security(self) -> Dict[str, Any]:
        return self._get_app_config().get("security", {})
    
    @property
    def registration(self) -> Dict[str, Any]:
        return self._get_app_config().get("registration", {})
    
    @property
    def informational_api(self) -> Dict[str, Any]:
        return self._get_app_config().get("informational_api", {})
    
    # ==========================================================================
    # FORM CONFIG SECTIONS - Dynamic (YAML or DB)
    # ==========================================================================
    
    @property
    def form(self) -> Dict[str, Any]:
        return self.config_loader.load_form_config()
    
    @property
    def steps(self) -> List[Dict[str, Any]]:
        return self.config_loader.load_steps()
    
    @property
    def fields(self) -> Dict[str, Any]:
        return self.config_loader.load_fields()
    
    @property
    def messages(self) -> Dict[str, Any]:
        return self.config_loader.load_messages()
    
    @property
    def commands(self) -> Dict[str, Any]:
        return self.config_loader.load_commands()
    
    # ==========================================================================
    # CONFIG SOURCE INFO
    # ==========================================================================
    
    @property
    def config_source(self) -> str:
        """Get current config source: 'yaml' or 'database'"""
        return self.config_loader.source.value
    
    def switch_config_source(self, source: str):
        """Switch config source at runtime"""
        self.config_loader.switch_source(ConfigSource(source))
    
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
        return self.server.get("informational_prefix", "/api/informational/v1")

    @property
    def transactional_prefix(self) -> str:
        return self.server.get("transactional_prefix", "/api/transactional/v1")
    
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
    
    def reload(self):
        """Reload all configs"""
        self._app_config = None
        reload_configs()


# Global settings instance
settings = Settings()


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 TESTING CONFIG LOADER")
    print("=" * 60)
    
    print(f"\n📋 Config Source: {settings.config_source}")
    print(f"📋 Fallback: {settings.config_loader.fallback.value}")
    
    print("\n--- App Config (always YAML) ---")
    print(f"  Debug: {settings.debug}")
    print(f"  Database URL: {settings.database_url[:30]}...")
    
    print("\n--- Form Config (from {}) ---".format(settings.config_source))
    
    print(f"\n  Steps ({len(settings.steps)}):")
    for step in settings.steps[:3]:
        print(f"    - {step.get('id')}: {step.get('name')}")
    
    print(f"\n  Fields ({len(settings.fields)}):")
    for field_id in list(settings.fields.keys())[:5]:
        field = settings.fields[field_id]
        print(f"    - {field_id}: {field.get('label')} ({field.get('type')})")
    
    print(f"\n  Messages: {len(settings.messages)} keys")
    print(f"  Commands: {len(settings.commands)} keys")
    
    print("\n" + "=" * 60)
    print("✅ Config test complete!")