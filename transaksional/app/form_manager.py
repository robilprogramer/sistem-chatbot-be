"""
Dynamic Form Manager
====================
Mengelola form configuration secara dinamis.
Semua steps dan fields dibaca dari config (YAML atau Database).
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import re
from transaksional.app.config import get_config_loader, settings


@dataclass
class FieldConfig:
    """Field configuration dari config source"""
    id: str
    label: str
    step: str
    type: str
    is_mandatory: bool = False
    validation: Dict[str, Any] = field(default_factory=dict)
    options: List[Dict[str, Any]] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    tips: str = ""
    extract_keywords: List[str] = field(default_factory=list)
    auto_formats: List[Dict[str, str]] = field(default_factory=list)
    auto_clean: bool = False
    default: Any = None
    raw_config: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, field_id: str, data: Dict[str, Any]) -> "FieldConfig":
        return cls(
            id=field_id,
            label=data.get("label", field_id),
            step=data.get("step", ""),
            type=data.get("type", "text"),
            is_mandatory=data.get("is_mandatory", False),
            validation=data.get("validation", {}),
            options=data.get("options", []),
            examples=data.get("examples", []),
            tips=data.get("tips", ""),
            extract_keywords=data.get("extract_keywords", []),
            auto_formats=data.get("auto_formats", []),
            auto_clean=data.get("auto_clean", False),
            default=data.get("default"),
            raw_config=data,
        )
    
    def get_example_text(self) -> str:
        if not self.examples:
            return ""
        text = f"📝 **{self.label}**\n\n"
        if self.validation.get("pattern"):
            text += f"Format: {self.tips}\n\n"
        text += "Contoh:\n"
        for ex in self.examples[:3]:
            text += f"  • {ex}\n"
        if self.tips:
            text += f"\n💡 Tips: {self.tips}"
        return text
    
    def normalize_value(self, value: str) -> str:
        if not value:
            return value
        value = str(value).strip()
        
        # Auto clean for phone
        if self.auto_clean and self.type == "phone":
            value = re.sub(r'[^0-9+]', '', value)
            
        # Match options/aliases
        if self.options:
            value_lower = value.lower()
            for opt in self.options:
                opt_value = opt.get("value", "")
                aliases = opt.get("aliases", [])
                if value_lower == opt_value.lower():
                    return opt_value
                if value_lower in [a.lower() for a in aliases]:
                    return opt_value
                    
        # Auto format conversion
        for auto_fmt in self.auto_formats:
            pattern = auto_fmt.get("pattern", "")
            if pattern and re.match(pattern, value, re.IGNORECASE):
                value = self._convert_format(value, auto_fmt.get("convert_to", ""))
                
        return value
    
    def _convert_format(self, value: str, target_format: str) -> str:
        if target_format == "DD/MM/YYYY":
            # YYYY-MM-DD -> DD/MM/YYYY
            if re.match(r'^\d{4}-\d{2}-\d{2}$', value):
                parts = value.split('-')
                return f"{parts[2]}/{parts[1]}/{parts[0]}"
            # "1 Januari 2020" -> DD/MM/YYYY
            months = {
                'januari': '01', 'februari': '02', 'maret': '03', 'april': '04',
                'mei': '05', 'juni': '06', 'juli': '07', 'agustus': '08',
                'september': '09', 'oktober': '10', 'november': '11', 'desember': '12'
            }
            match = re.match(r'(\d{1,2})\s+(\w+)\s+(\d{4})', value, re.IGNORECASE)
            if match:
                day = match.group(1).zfill(2)
                month = months.get(match.group(2).lower(), '01')
                year = match.group(3)
                return f"{day}/{month}/{year}"
        return value
    
    def validate(self, value: str) -> Tuple[bool, Optional[str]]:
        if not value:
            if self.is_mandatory:
                return False, f"{self.label} wajib diisi"
            return True, None
            
        # Pattern validation
        if pattern := self.validation.get("pattern"):
            if not re.match(pattern, value):
                return False, self.validation.get("error_message", f"{self.label} format tidak valid")
                
        # Length validation
        if min_len := self.validation.get("min_length"):
            if len(value) < min_len:
                return False, f"{self.label} minimal {min_len} karakter"
        if max_len := self.validation.get("max_length"):
            if len(value) > max_len:
                return False, f"{self.label} maksimal {max_len} karakter"
                
        # Age validation for date
        if self.type == "date":
            min_age = self.validation.get("min_age")
            max_age = self.validation.get("max_age")
            if min_age or max_age:
                is_valid, error = self._validate_age(value, min_age, max_age)
                if not is_valid:
                    return False, error
                    
        return True, None
    
    def _validate_age(self, date_str: str, min_age: int = None, max_age: int = None) -> Tuple[bool, Optional[str]]:
        try:
            match = re.match(r'(\d{2})/(\d{2})/(\d{4})', date_str)
            if not match:
                return False, "Format tanggal harus DD/MM/YYYY"
            day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            birth_date = datetime(year, month, day)
            today = datetime.now()
            age = today.year - birth_date.year
            if (today.month, today.day) < (birth_date.month, birth_date.day):
                age -= 1
            if min_age and age < min_age:
                return False, f"Usia minimal {min_age} tahun"
            if max_age and age > max_age:
                return False, f"Usia maksimal {max_age} tahun"
            return True, None
        except:
            return False, "Tanggal tidak valid"


@dataclass
class StepConfig:
    """Step configuration from config source"""
    id: str
    name: str
    description: str
    order: int
    is_mandatory: bool = True
    can_skip: bool = False
    skip_conditions: List[Dict[str, Any]] = field(default_factory=list)
    icon: str = ""
    raw_config: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepConfig":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            order=data.get("order", 0),
            is_mandatory=data.get("is_mandatory", True),
            can_skip=data.get("can_skip", False),
            skip_conditions=data.get("skip_conditions", []),
            icon=data.get("icon", ""),
            raw_config=data,
        )


class DynamicFormManager:
    """
    Dynamic form manager that loads config from YAML or Database.
    Uses DynamicConfigLoader under the hood.
    """
    
    def __init__(self):
        self._config_loader = None
        self._form_config = None
        self._steps: List[StepConfig] = []
        self._fields: Dict[str, FieldConfig] = {}
        self._messages: Dict[str, Any] = {}
        self._commands: Dict[str, Any] = {}
        self._load_config()
    
    @property
    def config(self) -> Dict[str, Any]:
        """Get raw config dictionary"""
        return self._form_config or {}
    
    @property
    def config_source(self) -> str:
        """Get current config source"""
        return self._config_loader.source.value if self._config_loader else "unknown"
    
    def _load_config(self):
        """Load configuration from dynamic source"""
        self._config_loader = get_config_loader()
        
        print(f"📋 FormManager loading config from: {self._config_loader.source.value}")
        
        # Load steps
        steps_data = self._config_loader.load_steps()
        self._steps = [StepConfig.from_dict(step_data) for step_data in steps_data]
        self._steps.sort(key=lambda s: s.order)
        print(f"   ✓ Loaded {len(self._steps)} steps")
        
        # Load fields
        fields_data = self._config_loader.load_fields()
        self._fields = {}
        for field_id, field_data in fields_data.items():
            self._fields[field_id] = FieldConfig.from_dict(field_id, field_data)
        print(f"   ✓ Loaded {len(self._fields)} fields")
        
        # Load messages
        self._messages = self._config_loader.load_messages()
        print(f"   ✓ Loaded messages")
        
        # Load commands
        self._commands = self._config_loader.load_commands()
        print(f"   ✓ Loaded {len(self._commands)} commands")
        
        # Store full config
        self._form_config = self._config_loader.load_full_config()
    
    def reload(self):
        """Reload configuration"""
        print("🔄 Reloading form configuration...")
        self._config_loader.reload()
        self._load_config()
    
    def switch_source(self, source: str):
        """Switch config source (yaml/database)"""
        from transaksional.app.config import ConfigSource
        self._config_loader.switch_source(ConfigSource(source))
        self._load_config()
    
    # ==========================================================================
    # STEP METHODS
    # ==========================================================================
    
    def get_steps(self) -> List[StepConfig]:
        return self._steps
    
    def get_step(self, step_id: str) -> Optional[StepConfig]:
        for step in self._steps:
            if step.id == step_id:
                return step
        return None
    
    def get_first_step(self) -> Optional[StepConfig]:
        return self._steps[0] if self._steps else None
    
    def get_next_step(self, current_step_id: str) -> Optional[StepConfig]:
        for i, step in enumerate(self._steps):
            if step.id == current_step_id and i + 1 < len(self._steps):
                return self._steps[i + 1]
        return None
    
    def get_previous_step(self, current_step_id: str) -> Optional[StepConfig]:
        for i, step in enumerate(self._steps):
            if step.id == current_step_id and i > 0:
                return self._steps[i - 1]
        return None
    
    def get_step_index(self, step_id: str) -> int:
        for i, step in enumerate(self._steps):
            if step.id == step_id:
                return i
        return -1
    
    # ==========================================================================
    # FIELD METHODS
    # ==========================================================================
    
    def get_field(self, field_id: str) -> Optional[FieldConfig]:
        return self._fields.get(field_id)
    
    def get_all_fields(self) -> List[FieldConfig]:
        return list(self._fields.values())
    
    def get_fields_for_step(self, step_id: str) -> List[FieldConfig]:
        return [f for f in self._fields.values() if f.step == step_id]
    
    def get_mandatory_fields_for_step(self, step_id: str) -> List[FieldConfig]:
        return [f for f in self.get_fields_for_step(step_id) if f.is_mandatory]
    
    def get_all_mandatory_fields(self) -> List[FieldConfig]:
        return [f for f in self._fields.values() if f.is_mandatory]
    
    def get_field_by_keyword(self, keyword: str) -> Optional[FieldConfig]:
        keyword_lower = keyword.lower()
        for field in self._fields.values():
            # Check extract_keywords
            if keyword_lower in [k.lower() for k in field.extract_keywords]:
                return field
            # Check field id
            if keyword_lower == field.id.lower():
                return field
            # Check label
            if keyword_lower in field.label.lower():
                return field
        return None
    
    def get_missing_mandatory_fields(self, step_id: str, collected_data: Dict[str, Any]) -> List[FieldConfig]:
        mandatory = self.get_mandatory_fields_for_step(step_id)
        return [f for f in mandatory if not collected_data.get(f.id)]
    
    def can_advance_from_step(self, step_id: str, collected_data: Dict[str, Any]) -> bool:
        return len(self.get_missing_mandatory_fields(step_id, collected_data)) == 0
    
    def get_field_example(self, field_id: str) -> str:
        field = self.get_field(field_id)
        return field.get_example_text() if field else ""
    
    # ==========================================================================
    # COMMAND & MESSAGE METHODS
    # ==========================================================================
    
    def detect_example_request(self, message: str) -> Optional[FieldConfig]:
        message_lower = message.lower()
        example_keywords = self._commands.get("example", {}).get("keywords", [])
        if not any(kw in message_lower for kw in example_keywords):
            return None
        for field in self._fields.values():
            for kw in field.extract_keywords:
                if kw.lower() in message_lower:
                    return field
            if field.label.lower() in message_lower:
                return field
        return None
    
    def detect_command(self, message: str) -> Optional[str]:
        print(f"Detecting command in message: {message}")
        message_lower = message.lower().strip()
        for cmd_name, cmd_config in self._commands.items():
            keywords = cmd_config.get("keywords", [])
            for kw in keywords:
                if kw in message_lower:
                    print(f"Detected command: {cmd_name}")
                    return cmd_name
        print(f"Detected command: None")
        return None
    
    def get_message(self, key: str, **kwargs) -> str:
        keys = key.split('.')
        value = self._messages
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, "")
            else:
                return ""
        if isinstance(value, str):
            try:
                return value.format(**kwargs)
            except KeyError:
                return value
        return str(value) if value else ""
    
    def get_welcome_message(self) -> str:
        return self.get_message("welcome")
    
    def get_step_transition_message(self, from_step: str, to_step: str) -> str:
        return self.get_message(f"step_transitions.{from_step}_to_{to_step}")
    
    # ==========================================================================
    # VALIDATION & COMPLETION
    # ==========================================================================
    
    def validate_field(self, field_id: str, value: str) -> Tuple[bool, Optional[str], str]:
        field = self.get_field(field_id)
        if not field:
            return True, None, value
        normalized = field.normalize_value(value)
        is_valid, error = field.validate(normalized)
        return is_valid, error, normalized
    
    def calculate_completion(self, collected_data: Dict[str, Any]) -> float:
        mandatory_fields = self.get_all_mandatory_fields()
        if not mandatory_fields:
            return 100.0
        filled = sum(1 for f in mandatory_fields if collected_data.get(f.id))
        return (filled / len(mandatory_fields)) * 100
    
    def get_minimum_completion(self) -> float:
        form_config = self._form_config.get("form", {})
        return form_config.get("confirmation", {}).get("min_completion_percentage", 60)
    
    def can_confirm(self, collected_data: Dict[str, Any]) -> Tuple[bool, str]:
        completion = self.calculate_completion(collected_data)
        min_completion = self.get_minimum_completion()
        if completion < min_completion:
            return False, f"Data baru {completion:.0f}% lengkap. Minimal {min_completion}%."
        
        form_config = self._form_config.get("form", {})
        require_all = form_config.get("confirmation", {}).get("require_all_mandatory_fields", False)
        if require_all:
            missing = [f.label for f in self.get_all_mandatory_fields() if not collected_data.get(f.id)]
            if missing:
                return False, f"Field wajib belum diisi: {', '.join(missing)}"
        return True, ""
    
    def should_skip_step(self, step_id: str, collected_data: Dict[str, Any]) -> bool:
        step = self.get_step(step_id)
        if not step or not step.skip_conditions:
            return False
        for condition in step.skip_conditions:
            for field_id, allowed_values in condition.items():
                if collected_data.get(field_id) in allowed_values:
                    return True
        return False
    
    # ==========================================================================
    # EXTRACTION HELPERS
    # ==========================================================================
    
    def extract_fields_simple(self, message: str, fields: List[FieldConfig]) -> Dict[str, Any]:
        """Simple extraction - FALLBACK ONLY when LLM fails"""
        result = {}
        for field in fields:
            value = None
            
            # Select type - match options
            if field.type == "select" and field.options:
                for opt in field.options:
                    opt_value = opt.get("value", "")
                    aliases = opt.get("aliases", [])
                    if re.search(rf'\b{re.escape(opt_value)}\b', message, re.IGNORECASE):
                        value = opt_value
                        break
                    for alias in aliases:
                        if re.search(rf'\b{re.escape(alias)}\b', message, re.IGNORECASE):
                            value = opt_value
                            break
                    if value:
                        break
                        
            # Date type
            elif field.type == "date":
                patterns = [
                    r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})',
                    r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
                    r'(\d{1,2}\s+(?:januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember)\s+\d{4})',
                ]
                for pattern in patterns:
                    match = re.search(pattern, message, re.IGNORECASE)
                    if match:
                        value = match.group(1)
                        break
                        
            # Phone type
            elif field.type == "phone":
                phone_clean = re.sub(r'[\s\-\(\)]', '', message)
                phone_match = re.search(r'(0\d{9,13}|\+62\d{9,12})', phone_clean)
                if phone_match:
                    value = phone_match.group(1)
                    
            # Email type
            elif field.type == "email":
                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', message)
                if email_match:
                    value = email_match.group(0)
                    
            # Number type
            elif field.type == "number":
                for kw in field.extract_keywords:
                    match = re.search(rf'{re.escape(kw)}\s*[:\s]*(\d+)', message, re.IGNORECASE)
                    if match:
                        value = match.group(1)
                        break
            
            if value:
                if isinstance(value, str):
                    value = re.sub(r'^[A-Za-z\s]+:\s*', '', value).strip()
                result[field.id] = value
                
        return result


# =============================================================================
# SINGLETON
# =============================================================================

_form_manager: Optional[DynamicFormManager] = None


def get_form_manager() -> DynamicFormManager:
    """Get singleton form manager"""
    global _form_manager
    if _form_manager is None:
        _form_manager = DynamicFormManager()
    return _form_manager


def reload_form_manager():
    """Force reload form manager"""
    global _form_manager
    if _form_manager:
        _form_manager.reload()
    else:
        _form_manager = DynamicFormManager()
    return _form_manager