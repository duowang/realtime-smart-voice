"""Configuration paths and validation, without initializing audio or networking."""

import json
import math
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_FILE = PROJECT_ROOT / "config" / "config.json"
TIMEOUT_DEFAULTS = {
    "conversation_timeout": 120,
    "silence_timeout": 8,
    "post_response_timeout": 6,
}


def load_config(path: str | Path = DEFAULT_CONFIG_FILE) -> dict:
    """Fail clearly on malformed configuration instead of silently using defaults."""
    path = Path(path).expanduser()
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot read configuration {path}: {error}") from error
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object")
    for name, default in TIMEOUT_DEFAULTS.items():
        value = config.setdefault(name, default)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"{name} must be a positive finite number of seconds")
    for name in ("realtime_model", "realtime_voice", "transcription_model"):
        if name in config and (not isinstance(config[name], str) or not config[name].strip()):
            raise ValueError(f"{name} must be a non-empty string")
    for name, default, lower, upper in (
        ("timer_alert_volume", 0.25, 0, 1),
        ("timer_alert_seconds", 10, 1, 30),
    ):
        value = config.setdefault(name, default)
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not lower <= value <= upper
        ):
            raise ValueError(f"{name} must be between {lower} and {upper}")
    path = config.setdefault("timer_store_path", "data/timers.json")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("timer_store_path must be a non-empty path")
    return config


def get_api_key(config: dict) -> str:
    """Keep shell environment precedence and parse .env as data, not shell code."""
    load_dotenv(PROJECT_ROOT / ".env")
    key = os.getenv("OPENAI_API_KEY") or config.get("openai_api_key")
    if not isinstance(key, str) or not key.strip() or key == "your_openai_api_key_here":
        raise ValueError("Set OPENAI_API_KEY in .env or the environment before starting")
    return key.strip()
