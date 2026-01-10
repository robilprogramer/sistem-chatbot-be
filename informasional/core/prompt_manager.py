from core.config_loader import PROMPT_CONFIG, APP_CONFIG

def get_mode() -> str:
    return APP_CONFIG["modes"]["default"]

def get_system_prompt() -> str:
    mode = get_mode()
    return PROMPT_CONFIG[mode]["system_prompt"]

def get_query_prompt() -> str:
    mode = get_mode()
    return PROMPT_CONFIG[mode]["query_prompt"]
