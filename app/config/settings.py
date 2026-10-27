"""Application settings, persisted in a local user settings file.

Credentials are intentionally excluded from this module.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

DEFAULT_MODELS = [
    "qwen-turbo",
    "qwen-plus",
    "qwen-max",
    "qwen-long",
    "qwen3-max-latest",
    "qwen3-235b-a22b-instruct-cosmo",
]

DEFAULT_MODEL = "qwen-turbo"

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant in a desktop chat app. "
    "Answer concisely and accurately. Use markdown where helpful."
)

PROVIDER_QWEN = "Qwen"
SUPPORTED_PROVIDERS = [PROVIDER_QWEN]


@dataclass
class AppSettings:
    provider: str = PROVIDER_QWEN
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    available_models: list[str] = field(default_factory=lambda: list(DEFAULT_MODELS))
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    request_timeout_seconds: float = 60.0
    theme: str = "dark"
    sidebar_width: int = 260
    chat_font_scale: float = 1.0
    max_context_messages: int = 40


SETTINGS_FILE_NAME = "settings.json"


def _settings_path() -> Path:
    data_dir = Path.home() / ".qwen-desktop-chat"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / SETTINGS_FILE_NAME


def load_settings(path: Optional[Path] = None) -> AppSettings:
    path = path or _settings_path()
    if not path.exists():
        return AppSettings()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return AppSettings()
    return _from_dict(data)


def save_settings(settings: AppSettings, path: Optional[Path] = None) -> Path:
    path = path or _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_to_dict(settings), f, indent=2, ensure_ascii=False)
    return path


def _to_dict(settings: AppSettings) -> dict:
    d = asdict(settings)
    d["temperature"] = float(d["temperature"])
    d["max_tokens"] = int(d["max_tokens"])
    d["request_timeout_seconds"] = float(d["request_timeout_seconds"])
    d["sidebar_width"] = int(d["sidebar_width"])
    d["chat_font_scale"] = float(d["chat_font_scale"])
    d["max_context_messages"] = int(d["max_context_messages"])
    d["available_models"] = list(d["available_models"])
    return d


def _from_dict(data: dict) -> AppSettings:
    allowed = {
        "provider",
        "base_url",
        "model",
        "available_models",
        "temperature",
        "max_tokens",
        "system_prompt",
        "request_timeout_seconds",
        "theme",
        "sidebar_width",
        "chat_font_scale",
        "max_context_messages",
    }
    data = {k: v for k, v in data.items() if k in allowed}
    defaults = AppSettings()
    defaults.__dict__.update(data)
    if not getattr(defaults, "available_models", None):
        defaults.available_models = list(DEFAULT_MODELS)
    if not defaults.provider:
        defaults.provider = PROVIDER_QWEN
    if not defaults.base_url:
        defaults.base_url = DEFAULT_BASE_URL
    if not defaults.model:
        defaults.model = DEFAULT_MODEL
    if not defaults.system_prompt:
        defaults.system_prompt = DEFAULT_SYSTEM_PROMPT
    # Temperature 0.0 is a legitimate, deterministic setting, so only a
    # negative value is treated as invalid.
    if defaults.temperature < 0:
        defaults.temperature = 0.7
    if defaults.temperature > 2.0:
        defaults.temperature = 2.0
    if defaults.max_tokens <= 0:
        defaults.max_tokens = 4096
    if defaults.request_timeout_seconds <= 0:
        defaults.request_timeout_seconds = 60.0
    if defaults.theme not in ("dark", "light"):
        defaults.theme = "dark"
    if defaults.sidebar_width < 180:
        defaults.sidebar_width = 260
    if not (0.5 <= defaults.chat_font_scale <= 2.0):
        defaults.chat_font_scale = 1.0
    try:
        context = int(defaults.max_context_messages)
    except (TypeError, ValueError):
        context = 40
    defaults.max_context_messages = min(200, max(4, context))
    return defaults
