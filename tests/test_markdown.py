"""Tests for markdown rendering, code block splitting and sanitizing."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ui.markdown_widget import (
    render_markdown,
    sanitize_html,
    set_render_theme,
    split_segments,
)


class TestSplitSegments(unittest.TestCase):
    def test_plain_text(self) -> None:
        segments = split_segments("just text")
        self.assertEqual(segments, [("text", "", "just text")])

    def test_single_code_block(self) -> None:
        segments = split_segments("```python\nprint('hi')\n```")
        self.assertEqual([s[0] for s in segments], ["code"])
        self.assertEqual(segments[0][1], "python")
        self.assertEqual(segments[0][2], "print('hi')")

    def test_text_then_code_then_text(self) -> None:
        source = "before\n```js\nlet a = 1;\n```\nafter"
        segments = split_segments(source)
        self.assertEqual([s[0] for s in segments], ["text", "code", "text"])
        self.assertEqual(segments[1][1], "js")

    def test_unclosed_fence_keeps_content(self) -> None:
        """A half-streamed code block must not lose its text."""
        segments = split_segments("```python\nprint('partial')")
        self.assertEqual(segments[0][0], "code")
        self.assertEqual(segments[0][2], "print('partial')")

    def test_code_block_without_language(self) -> None:
        segments = split_segments("```\nplain\n```")
        self.assertEqual(segments[0][0], "code")
        self.assertEqual(segments[0][1], "")

    def test_empty_source(self) -> None:
        self.assertEqual(split_segments(""), [])


class TestSanitize(unittest.TestCase):
    def test_removes_script_tag(self) -> None:
        cleaned = sanitize_html('<p>ok</p><script>alert(1)</script>')
        self.assertNotIn("<script", cleaned.lower())
        self.assertIn("ok", cleaned)

    def test_removes_event_handler(self) -> None:
        cleaned = sanitize_html('<img src="x" onerror="alert(1)">')
        self.assertNotIn("onerror", cleaned.lower())

    def test_removes_iframe(self) -> None:
        cleaned = sanitize_html('<iframe src="http://evil"></iframe>')
        self.assertNotIn("<iframe", cleaned.lower())

    def test_removes_javascript_url(self) -> None:
        cleaned = sanitize_html('<a href="javascript:alert(1)">x</a>')
        self.assertNotIn("javascript:", cleaned.lower())

    def test_keeps_normal_markup(self) -> None:
        cleaned = sanitize_html("<p><strong>bold</strong></p>")
        self.assertIn("<strong>bold</strong>", cleaned)


class TestRenderMarkdown(unittest.TestCase):
    def tearDown(self) -> None:
        set_render_theme("dark")

    def test_renders_table(self) -> None:
        """Tables are an explicit product requirement; nl2br must not break them."""
        html = render_markdown("| a | b |\n|---|---|\n| 1 | 2 |")
        self.assertIn("<table", html)
        self.assertIn("<th", html)
        self.assertIn("<td", html)

    def test_renders_headings_and_lists(self) -> None:
        html = render_markdown("# Title\n\n- one\n- two")
        self.assertIn("<h1", html)
        self.assertIn("<ul", html)

    def test_renders_bold_and_inline_code(self) -> None:
        html = render_markdown("**bold** and `code`")
        self.assertIn("<strong>", html)
        self.assertIn("<code>", html)

    def test_renders_fenced_code(self) -> None:
        html = render_markdown("```python\nprint(1)\n```")
        self.assertIn("<pre", html)

    def test_strips_script_from_model_output(self) -> None:
        html = render_markdown("hello\n\n<script>alert('x')</script>")
        self.assertNotIn("<script", html.lower())

    def test_escapes_html_in_code_block(self) -> None:
        html = render_markdown("```\n<b>not bold</b>\n```")
        self.assertNotIn("<b>not bold</b>", html)

    def test_theme_colors_are_applied(self) -> None:
        set_render_theme("light")
        light_html = render_markdown("text")
        set_render_theme("dark")
        dark_html = render_markdown("text")
        self.assertNotEqual(light_html, dark_html)


class TestHighlightedCodeBlock(unittest.TestCase):
    def test_highlight_code_returns_markup(self) -> None:
        from app.ui.markdown_widget import highlight_code

        html = highlight_code("print('x')", "python")
        self.assertIn("print", html)
        self.assertIn("<pre", html)

    def test_highlight_unknown_language_falls_back(self) -> None:
        from app.ui.markdown_widget import highlight_code

        html = highlight_code("some text", "definitely-not-a-language")
        self.assertIn("some text", html)

    def test_highlight_escapes_html_when_no_lexer(self) -> None:
        from app.ui.markdown_widget import highlight_code

        html = highlight_code("<script>bad</script>", "")
        self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()
