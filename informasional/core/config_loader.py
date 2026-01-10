import yaml
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def load_yaml(path: str) -> dict:
    with open(BASE_DIR / path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# Global config
APP_CONFIG = load_yaml("config/config.yaml")
PROMPT_CONFIG = load_yaml("config/prompts.yaml")
