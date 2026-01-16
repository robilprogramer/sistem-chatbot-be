"""
Dynamic Config Loader - Support YAML & Database
================================================
Bisa switch antara YAML file atau PostgreSQL database sebagai source config.
Support hot-reload dan caching.
"""

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
from abc import ABC, abstractmethod
import asyncio

load_dotenv()


class ConfigSource(str, Enum):
    YAML = "yaml"
    DATABASE = "database"
    

class BaseConfigProvider(ABC):
    """Abstract base class for config providers"""
    
    @abstractmethod
    def load_form_config(self) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def load_steps(self) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def load_fields(self) -> Dict[str, Dict[str, Any]]:
        pass
    
    @abstractmethod
    def load_messages(self) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def load_commands(self) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def save_form_config(self, config: Dict[str, Any]) -> bool:
        pass


class YAMLConfigProvider(BaseConfigProvider):
    """Load config from YAML files"""
    
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "config"
        self.config_dir = Path(config_dir)
        self._cache: Dict[str, Any] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=5)  # Cache TTL
    
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
    
    def _load_yaml(self, filename: str, use_cache: bool = True) -> Dict[str, Any]:
        if not filename.endswith('.yaml') and not filename.endswith('.yml'):
            filename = f"{filename}.yaml"
        
        cache_key = filename
        
        if use_cache and cache_key in self._cache and self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        filepath = self.config_dir / filename
        
        if not filepath.exists():
            raise FileNotFoundError(f"Config file not found: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        config = self._substitute_env_vars(config)
        
        if use_cache:
            self._cache[cache_key] = config
            self._cache_time[cache_key] = datetime.now()
            
        return config
    
    def load_form_config(self) -> Dict[str, Any]:
        config = self._load_yaml("form_config")
        return config.get("form", {})
    
    def load_steps(self) -> List[Dict[str, Any]]:
        config = self._load_yaml("form_config")
        return config.get("steps", [])
    
    def load_fields(self) -> Dict[str, Dict[str, Any]]:
        config = self._load_yaml("form_config")
        return config.get("fields", {})
    
    def load_messages(self) -> Dict[str, Any]:
        config = self._load_yaml("form_config")
        return config.get("messages", {})
    
    def load_commands(self) -> Dict[str, Any]:
        config = self._load_yaml("form_config")
        return config.get("commands", {})
    
    def load_full_config(self) -> Dict[str, Any]:
        """Load complete form_config.yaml"""
        return self._load_yaml("form_config")
    
    def save_form_config(self, config: Dict[str, Any]) -> bool:
        """Save config back to YAML (for sync purposes)"""
        try:
            filepath = self.config_dir / "form_config.yaml"
            with open(filepath, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            self.reload()
            return True
        except Exception as e:
            print(f"Error saving YAML config: {e}")
            return False
    
    def reload(self):
        """Clear cache to force reload"""
        self._cache.clear()
        self._cache_time.clear()


class DatabaseConfigProvider(BaseConfigProvider):
    """Load config from PostgreSQL database"""
    
    def __init__(self, db_url: str = None):
        self.db_url = db_url or os.getenv("DATABASE_URL")
        self._engine = None
        self._cache: Dict[str, Any] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=2)  # Shorter TTL for DB
    
    @property
    def engine(self):
        if self._engine is None:
            from sqlalchemy import create_engine
            self._engine = create_engine(self.db_url)
        return self._engine
    
    def _is_cache_valid(self, key: str) -> bool:
        if key not in self._cache_time:
            return False
        return datetime.now() - self._cache_time[key] < self._cache_ttl
    
    def _execute_query(self, query: str, params: Dict = None) -> List[Dict]:
        from sqlalchemy import text
        with self.engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            return [dict(row._mapping) for row in result]
    
    def _get_active_config_id(self) -> Optional[int]:
        """Get currently active form config ID"""
        result = self._execute_query(
            "SELECT id FROM form_configs WHERE is_active = true ORDER BY updated_at DESC LIMIT 1"
        )
        return result[0]['id'] if result else None
    
    def load_form_config(self) -> Dict[str, Any]:
        cache_key = "form_config"
        if cache_key in self._cache and self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        result = self._execute_query("""
            SELECT config_data FROM form_configs 
            WHERE is_active = true 
            ORDER BY updated_at DESC LIMIT 1
        """)
        
        if result:
            config = result[0]['config_data']
            if isinstance(config, str):
                config = json.loads(config)
            form_config = config.get("form", config)
            self._cache[cache_key] = form_config
            self._cache_time[cache_key] = datetime.now()
            return form_config
        
        return {}
    
    def load_steps(self) -> List[Dict[str, Any]]:
        cache_key = "steps"
        if cache_key in self._cache and self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        config_id = self._get_active_config_id()
        if not config_id:
            return []
        
        result = self._execute_query("""
            SELECT step_id, step_name, description, step_order, is_mandatory, 
                   can_skip, skip_conditions, icon
            FROM form_steps 
            WHERE config_id = :config_id AND is_active = true
            ORDER BY step_order
        """, {"config_id": config_id})
        
        steps = []
        for row in result:
            steps.append({
                "id": row["step_id"],
                "name": row["step_name"],
                "description": row["description"],
                "order": row["step_order"],
                "is_mandatory": row["is_mandatory"],
                "can_skip": row["can_skip"],
                "skip_conditions": row["skip_conditions"] or [],
                "icon": row["icon"]
            })
        
        self._cache[cache_key] = steps
        self._cache_time[cache_key] = datetime.now()
        return steps
    
    def load_fields(self) -> Dict[str, Dict[str, Any]]:
        cache_key = "fields"
        if cache_key in self._cache and self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        config_id = self._get_active_config_id()
        if not config_id:
            return {}
        
        result = self._execute_query("""
            SELECT field_id, step_id, field_label, field_type, is_mandatory,
                   validation, options, examples, tips, extract_keywords,
                   auto_formats, auto_clean, default_value
            FROM form_fields 
            WHERE config_id = :config_id AND is_active = true
            ORDER BY field_order
        """, {"config_id": config_id})
        
        fields = {}
        for row in result:
            fields[row["field_id"]] = {
                "label": row["field_label"],
                "step": row["step_id"],
                "type": row["field_type"],
                "is_mandatory": row["is_mandatory"],
                "validation": row["validation"] or {},
                "options": row["options"] or [],
                "examples": row["examples"] or [],
                "tips": row["tips"],
                "extract_keywords": row["extract_keywords"] or [],
                "auto_formats": row["auto_formats"] or [],
                "auto_clean": row["auto_clean"],
                "default": row["default_value"]
            }
        
        self._cache[cache_key] = fields
        self._cache_time[cache_key] = datetime.now()
        return fields
    
    def load_messages(self) -> Dict[str, Any]:
        cache_key = "messages"
        if cache_key in self._cache and self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        config_id = self._get_active_config_id()
        if not config_id:
            return {}
        
        result = self._execute_query("""
            SELECT message_key, message_template
            FROM form_messages 
            WHERE config_id = :config_id AND is_active = true
        """, {"config_id": config_id})
        
        # Convert flat keys to nested dict
        messages = {}
        for row in result:
            keys = row["message_key"].split(".")
            current = messages
            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]
            current[keys[-1]] = row["message_template"]
        
        self._cache[cache_key] = messages
        self._cache_time[cache_key] = datetime.now()
        return messages
    
    def load_commands(self) -> Dict[str, Any]:
        cache_key = "commands"
        if cache_key in self._cache and self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        config_id = self._get_active_config_id()
        if not config_id:
            return {}
        
        result = self._execute_query("""
            SELECT command_name, keywords, pattern
            FROM form_commands 
            WHERE config_id = :config_id AND is_active = true
        """, {"config_id": config_id})
        
        commands = {}
        for row in result:
            commands[row["command_name"]] = {
                "keywords": row["keywords"] or [],
                "pattern": row["pattern"]
            }
        
        self._cache[cache_key] = commands
        self._cache_time[cache_key] = datetime.now()
        return commands
    
    def save_form_config(self, config: Dict[str, Any]) -> bool:
        """Save config to database"""
        from sqlalchemy import text
        try:
            with self.engine.connect() as conn:
                # Deactivate old configs
                conn.execute(text("UPDATE form_configs SET is_active = false"))
                
                # Insert new config
                conn.execute(text("""
                    INSERT INTO form_configs (config_key, config_data, version, is_active)
                    VALUES (:key, :data, :version, true)
                """), {
                    "key": f"form_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "data": json.dumps(config),
                    "version": config.get("form", {}).get("version", "1.0.0")
                })
                conn.commit()
            
            self.reload()
            return True
        except Exception as e:
            print(f"Error saving DB config: {e}")
            return False
    
    def sync_from_yaml(self, yaml_provider: YAMLConfigProvider) -> bool:
        """Sync database from YAML file"""
        try:
            full_config = yaml_provider.load_full_config()
            return self.save_form_config(full_config)
        except Exception as e:
            print(f"Error syncing from YAML: {e}")
            return False
    
    def reload(self):
        """Clear cache to force reload"""
        self._cache.clear()
        self._cache_time.clear()


class DynamicConfigLoader:
    """
    Main config loader that can switch between YAML and Database.
    Supports fallback and auto-sync.
    """
    
    def __init__(self, 
                 source: ConfigSource = ConfigSource.YAML,
                 fallback: ConfigSource = ConfigSource.YAML,
                 config_dir: str = None,
                 db_url: str = None,
                 auto_sync: bool = False):
        self.source = source
        self.fallback = fallback
        self.auto_sync = auto_sync
        
        # Initialize providers
        self._yaml_provider = YAMLConfigProvider(config_dir)
        self._db_provider = None
        
        if source == ConfigSource.DATABASE or fallback == ConfigSource.DATABASE:
            try:
                self._db_provider = DatabaseConfigProvider(db_url)
            except Exception as e:
                print(f"Warning: Could not initialize DB provider: {e}")
        
        # Auto-sync from YAML to DB if enabled
        if auto_sync and self._db_provider and source == ConfigSource.DATABASE:
            self._auto_sync_to_db()
    
    @property
    def provider(self) -> BaseConfigProvider:
        """Get current active provider"""
        if self.source == ConfigSource.DATABASE and self._db_provider:
            return self._db_provider
        return self._yaml_provider
    
    @property
    def fallback_provider(self) -> BaseConfigProvider:
        """Get fallback provider"""
        if self.fallback == ConfigSource.DATABASE and self._db_provider:
            return self._db_provider
        return self._yaml_provider
    
    def _auto_sync_to_db(self):
        """Auto sync YAML to database"""
        try:
            if self._db_provider and self._yaml_provider:
                self._db_provider.sync_from_yaml(self._yaml_provider)
                print("✅ Auto-synced YAML config to database")
        except Exception as e:
            print(f"⚠️ Auto-sync failed: {e}")
    
    def _try_with_fallback(self, method_name: str, *args, **kwargs):
        """Try primary source, fallback if fails"""
        try:
            method = getattr(self.provider, method_name)
            return method(*args, **kwargs)
        except Exception as e:
            print(f"Primary source failed ({method_name}): {e}")
            if self.fallback != self.source:
                try:
                    method = getattr(self.fallback_provider, method_name)
                    return method(*args, **kwargs)
                except Exception as e2:
                    print(f"Fallback also failed: {e2}")
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
        """Load complete config (all sections)"""
        if isinstance(self.provider, YAMLConfigProvider):
            return self.provider.load_full_config()
        
        # For DB, reconstruct full config
        return {
            "form": self.load_form_config(),
            "steps": self.load_steps(),
            "fields": self.load_fields(),
            "messages": self.load_messages(),
            "commands": self.load_commands()
        }
    
    def switch_source(self, new_source: ConfigSource):
        """Switch config source at runtime"""
        self.source = new_source
        print(f"Switched config source to: {new_source.value}")
    
    def reload(self):
        """Reload all providers"""
        self._yaml_provider.reload()
        if self._db_provider:
            self._db_provider.reload()
    
    def sync_yaml_to_db(self) -> bool:
        """Manually sync YAML to database"""
        if not self._db_provider:
            print("Database provider not available")
            return False
        return self._db_provider.sync_from_yaml(self._yaml_provider)
    
    def sync_db_to_yaml(self) -> bool:
        """Sync database to YAML file"""
        if not self._db_provider:
            print("Database provider not available")
            return False
        
        try:
            full_config = {
                "form": self._db_provider.load_form_config(),
                "steps": self._db_provider.load_steps(),
                "fields": self._db_provider.load_fields(),
                "messages": self._db_provider.load_messages(),
                "commands": self._db_provider.load_commands()
            }
            return self._yaml_provider.save_form_config(full_config)
        except Exception as e:
            print(f"Error syncing to YAML: {e}")
            return False


# =============================================================================
# SINGLETON & HELPER FUNCTIONS
# =============================================================================

_config_loader: Optional[DynamicConfigLoader] = None


def get_config_loader(
    source: ConfigSource = None,
    config_dir: str = None,
    db_url: str = None,
    force_new: bool = False
) -> DynamicConfigLoader:
    """Get singleton config loader"""
    global _config_loader
    
    if _config_loader is None or force_new:
        # Get source from environment or system settings
        if source is None:
            source_str = os.getenv("FORM_CONFIG_SOURCE", "yaml").lower()
            source = ConfigSource(source_str) if source_str in ["yaml", "database"] else ConfigSource.YAML
        
        fallback_str = os.getenv("FORM_CONFIG_FALLBACK", "yaml").lower()
        fallback = ConfigSource(fallback_str) if fallback_str in ["yaml", "database"] else ConfigSource.YAML
        
        auto_sync = os.getenv("FORM_CONFIG_AUTO_SYNC", "false").lower() == "true"
        
        _config_loader = DynamicConfigLoader(
            source=source,
            fallback=fallback,
            config_dir=config_dir,
            db_url=db_url,
            auto_sync=auto_sync
        )
    
    return _config_loader


def get_form_config() -> Dict[str, Any]:
    """Get complete form config - backward compatible"""
    loader = get_config_loader()
    return loader.load_full_config()


def reload_configs():
    """Reload all configurations"""
    loader = get_config_loader()
    loader.reload()


# =============================================================================
# SETTINGS CLASS (Backward Compatible)
# =============================================================================

class Settings:
    """Quick access to settings with proper property definitions"""
    
    def __init__(self):
        self._app_config = None
        self._form_config_loader = None
    
    def _get_app_config(self) -> Dict[str, Any]:
        if self._app_config is None:
            yaml_provider = YAMLConfigProvider()
            self._app_config = yaml_provider._load_yaml("app_config")
        return self._app_config
    
    @property
    def config_loader(self) -> DynamicConfigLoader:
        if self._form_config_loader is None:
            self._form_config_loader = get_config_loader()
        return self._form_config_loader
    
    # ==========================================================================
    # RAW CONFIG SECTIONS - APP
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
    # COMMON SHORTCUTS
    # ==========================================================================
    
    @property
    def debug(self) -> bool:
        return self.app.get("debug", False)
    
    @property
    def host(self) -> str:
        return self.server.get("host", "0.0.0.0")
    
    @property
    def port(self) -> int:
        return self.server.get("port", 8000)
    
    @property
    def transactional_prefix(self) -> str:
        return self.server.get("transactional_prefix", "/api/transactional/v1")
    
    @property
    def database_url(self) -> str:
        return self.database.get("url", "")
    
    @property
    def config_source(self) -> str:
        """Get current config source: 'yaml' or 'database'"""
        return self.config_loader.source.value
    
    def switch_config_source(self, source: str):
        """Switch config source at runtime"""
        self.config_loader.switch_source(ConfigSource(source))
    
    def reload(self):
        """Reload all configs"""
        self._app_config = None
        self.config_loader.reload()


# Global settings instance
settings = Settings()


if __name__ == "__main__":
    print("=== Testing Dynamic Config Loader ===\n")
    
    # Test YAML loading
    print("1. Testing YAML provider:")
    yaml_provider = YAMLConfigProvider()
    try:
        form = yaml_provider.load_form_config()
        print(f"   Form ID: {form.get('id')}")
        print(f"   Steps count: {len(yaml_provider.load_steps())}")
    except FileNotFoundError:
        print("   (form_config.yaml not found)")
    
    # Test dynamic loader
    print("\n2. Testing Dynamic Loader:")
    loader = get_config_loader()
    print(f"   Current source: {loader.source.value}")
    print(f"   Fallback: {loader.fallback.value}")
    
    # Test settings
    print("\n3. Testing Settings:")
    print(f"   Config source: {settings.config_source}")
    print(f"   Debug mode: {settings.debug}")