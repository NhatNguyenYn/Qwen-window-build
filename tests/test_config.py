"""Tests for application settings."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.settings import (
    AppSettings,
    load_settings,
    save_settings,
    _to_dict,
    _from_dict,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
)


class TestSettings(unittest.TestCase):
    def test_defaults(self) -> None:
        s = AppSettings()
        self.assertEqual(s.provider, "Qwen")
        self.assertEqual(s.base_url, DEFAULT_BASE_URL)
        self.assertEqual(s.model, DEFAULT_MODEL)
        self.assertEqual(s.theme, "dark")

    def test_roundtrip_file(self) -> None:
        tmp = Path(tempfile.mktemp(suffix=".json"))
        try:
            s = AppSettings(temperature=0.2, max_tokens=512, theme="light")
            save_settings(s, tmp)
            loaded = load_settings(tmp)
            self.assertEqual(loaded.temperature, 0.2)
            self.assertEqual(loaded.max_tokens, 512)
            self.assertEqual(loaded.theme, "light")
        finally:
            try:
                os.remove(str(tmp))
            except Exception:
                pass

    def test_corrupt_file_falls_back(self) -> None:
        tmp = Path(tempfile.mktemp(suffix=".json"))
        try:
            tmp.write_text("not json{{{", encoding="utf-8")
            s = load_settings(tmp)
            self.assertEqual(s.theme, "dark")
        finally:
            try:
                os.remove(str(tmp))
            except Exception:
                pass

    def test_to_dict_and_from_dict(self) -> None:
        s = AppSettings(
            provider="Qwen",
            base_url="https://example.invalid/v1",
            model="qwen-plus",
            temperature=0.5,
            max_tokens=2048,
            system_prompt="Be helpful.",
            request_timeout_seconds=30.0,
            theme="light",
            sidebar_width=300,
            chat_font_scale=1.1,
            available_models=["qwen-turbo", "qwen-plus"],
        )
        d = _to_dict(s)
        rebuilt = _from_dict(d)
        self.assertEqual(rebuilt.provider, s.provider)
        self.assertEqual(rebuilt.base_url, s.base_url)
        self.assertEqual(rebuilt.model, s.model)
        self.assertEqual(rebuilt.temperature, s.temperature)
        self.assertEqual(rebuilt.max_tokens, s.max_tokens)
        self.assertEqual(rebuilt.system_prompt, s.system_prompt)
        self.assertEqual(rebuilt.request_timeout_seconds, s.request_timeout_seconds)
        self.assertEqual(rebuilt.theme, s.theme)
        self.assertEqual(rebuilt.sidebar_width, s.sidebar_width)
        self.assertEqual(rebuilt.chat_font_scale, s.chat_font_scale)

    def test_clamp_invalid_values(self) -> None:
        bad = _from_dict({
            "temperature": -1,
            "max_tokens": 0,
            "request_timeout_seconds": -5,
            "theme": "cyan",
            "provider": "",
            "base_url": "",
            "model": "",
            "sidebar_width": 10,
            "chat_font_scale": 5.0,
        })
        self.assertEqual(bad.temperature, 0.7)
        self.assertEqual(bad.max_tokens, 4096)
        self.assertEqual(bad.request_timeout_seconds, 60.0)
        self.assertEqual(bad.theme, "dark")
        self.assertEqual(bad.provider, "Qwen")
        self.assertEqual(bad.base_url, DEFAULT_BASE_URL)
        self.assertEqual(bad.model, DEFAULT_MODEL)
        self.assertEqual(bad.sidebar_width, 260)
        self.assertEqual(bad.chat_font_scale, 1.0)

    def test_available_models_persist(self) -> None:
        s = _from_dict({
            "available_models": ["qwen-turbo", "qwen-custom"],
            "provider": "Qwen",
            "base_url": DEFAULT_BASE_URL,
            "model": "qwen-custom",
        })
        self.assertIn("qwen-custom", s.available_models)
        self.assertEqual(s.model, "qwen-custom")


if __name__ == "__main__":
    unittest.main()
