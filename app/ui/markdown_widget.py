"""Markdown rendering with syntax-highlighted code blocks.

Design notes:

* Prose and code are rendered by different widgets. Prose goes into a
  ``QTextBrowser`` (tables, lists, headings, links). Each fenced code block
  becomes its own :class:`CodeBlockWidget` so it can carry its own Copy button,
  which a single rich-text document cannot provide.
* Model output is treated as data. It is parsed as markdown and rendered as
  rich text; ``QTextBrowser`` has no scripting engine, and unsafe tags are
  stripped before rendering, so returned content cannot execute.
"""
from __future__ import annotations

import re
from html import escape as _escape

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:  # Pygments is optional; code still renders without it.
    from pygments import highlight as _pygments_highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.util import ClassNotFound

    _HAS_PYGMENTS = True
except Exception:  # pragma: no cover - depends on the installed environment
    _HAS_PYGMENTS = False

    class ClassNotFound(Exception):  # type: ignore[no-redef]
        pass


_FENCE_RE = re.compile(r"^\s*```+\s*([A-Za-z0-9_+\-.#]*)\s*$")

_UNSAFE_PATTERNS = (
    re.compile(r"<\s*script.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<\s*(iframe|object|embed|link|meta|style)\b[^>]*>", re.IGNORECASE),
    re.compile(r"\son[a-z]+\s*=\s*\"[^\"]*\"", re.IGNORECASE),
    re.compile(r"\son[a-z]+\s*=\s*'[^']*'", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
)

_THEMES = {
    "dark": {
        "text": "#d4d4d8",
        "muted": "#a1a1aa",
        "border": "#3f3f46",
        "code_bg": "#111113",
        "code_text": "#d4d4d8",
        "accent": "#4ade80",
        "link": "#7dd3fc",
    },
    "light": {
        "text": "#27272a",
        "muted": "#52525b",
        "border": "#d4d4d8",
        "code_bg": "#f4f4f5",
        "code_text": "#1f2937",
        "accent": "#16a34a",
        "link": "#0369a1",
    },
}

_current_theme = "dark"


def set_render_theme(theme: str) -> None:
    """Set the palette used by subsequently created widgets."""
    global _current_theme
    _current_theme = "light" if theme == "light" else "dark"


def current_theme() -> str:
    return _current_theme


def _palette() -> dict:
    return _THEMES.get(_current_theme, _THEMES["dark"])


def sanitize_html(html: str) -> str:
    """Strip constructs that could load or execute remote content."""
    cleaned = html
    for pattern in _UNSAFE_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return cleaned


def highlight_code(code: str, language: str = "") -> str:
    """Return HTML for one code block, highlighted when possible."""
    if not _HAS_PYGMENTS:
        return (
            f'<pre style="margin:0;"><code>{_escape(code)}</code></pre>'
        )
    lexer = None
    if language:
        try:
            lexer = get_lexer_by_name(language, stripall=False)
        except ClassNotFound:
            lexer = None
    if lexer is None:
        try:
            lexer = guess_lexer(code)
        except Exception:
            lexer = None
    if lexer is None:
        return f'<pre style="margin:0;"><code>{_escape(code)}</code></pre>'
    formatter = HtmlFormatter(nowrap=True, noclasses=True)
    try:
        body = _pygments_highlight(code, lexer, formatter)
    except Exception:
        return f'<pre style="margin:0;"><code>{_escape(code)}</code></pre>'
    return f'<pre style="margin:0;white-space:pre-wrap;"><code>{body}</code></pre>'


def render_markdown(source: str) -> str:
    """Render markdown source into safe HTML.

    Fenced code blocks are replaced by highlighted HTML. Prose is rendered with
    python-markdown so tables, lists and headings behave correctly, then the
    result is sanitized.
    """
    import markdown as markdown_lib

    colors = _palette()
    body = markdown_lib.markdown(
        source,
        extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
    )
    body = sanitize_html(body)
    return (
        f'<div style="color:{colors["text"]};font-size:13px;line-height:1.6;">'
        f"{body}</div>"
    )


def split_segments(source: str) -> list[tuple[str, str, str]]:
    """Split markdown into ``(kind, language, text)`` segments.

    ``kind`` is ``"text"`` or ``"code"``. Unclosed fences are treated as code so
    a partially streamed answer does not lose its content.
    """
    segments: list[tuple[str, str, str]] = []
    buffer: list[str] = []
    in_code = False
    language = ""

    for line in source.splitlines():
        match = _FENCE_RE.match(line)
        if match:
            if in_code:
                segments.append(("code", language, "\n".join(buffer)))
                buffer = []
                in_code = False
                language = ""
            else:
                if buffer:
                    segments.append(("text", "", "\n".join(buffer)))
                    buffer = []
                in_code = True
                language = match.group(1) or ""
            continue
        buffer.append(line)

    if buffer:
        kind = "code" if in_code else "text"
        segments.append((kind, language if in_code else "", "\n".join(buffer)))
    return segments


class CodeBlockWidget(QWidget):
    """One syntax-highlighted code block with its own Copy button."""

    def __init__(self, code: str, language: str = "") -> None:
        super().__init__()
        self._code = code
        colors = _palette()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(
            f"background-color: {colors['code_bg']};"
            f"border-top-left-radius: 8px; border-top-right-radius: 8px;"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 4, 6, 4)
        header_layout.setSpacing(8)

        label = QLabel(language or "code")
        label.setStyleSheet(
            f"color: {colors['muted']}; font-size: 11px; background: transparent;"
        )
        header_layout.addWidget(label, 1)

        copy_btn = QToolButton()
        copy_btn.setText("Copy")
        copy_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setStyleSheet(
            f"QToolButton {{ color: {colors['muted']}; background: transparent;"
            f" border: none; padding: 2px 8px; border-radius: 5px; font-size: 11px; }}"
            f"QToolButton:hover {{ color: {colors['accent']};"
            f" background-color: rgba(127,127,127,0.15); }}"
        )
        copy_btn.clicked.connect(self.copy_to_clipboard)
        header_layout.addWidget(copy_btn, 0, Qt.AlignRight)

        outer.addWidget(header)

        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        self._view.setPlainText(code)
        self._view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._view.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {colors['code_bg']};"
            f" color: {colors['code_text']}; border: 1px solid {colors['border']};"
            f" border-top: none; border-bottom-left-radius: 8px;"
            f" border-bottom-right-radius: 8px; padding: 8px;"
            f" font-family: Consolas, 'Cascadia Mono', monospace; font-size: 12px; }}"
        )
        line_count = max(1, code.count("\n") + 1)
        self._view.setFixedHeight(min(420, 24 + line_count * 17))
        outer.addWidget(self._view)

        self._copy_btn = copy_btn

    def copy_to_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._code)
        self._copy_btn.setText("Copied")
        self._copy_btn.setStyleSheet(
            f"QToolButton {{ color: {_palette()['accent']}; background: transparent;"
            f" border: none; padding: 2px 8px; font-size: 11px; }}"
        )


class MarkdownWidget(QWidget):
    """Render one markdown document as stacked prose and code block widgets."""

    MAX_LIVE_RENDER_CHARS = 150_000

    def __init__(self, source: str = "", *, plain: bool = False) -> None:
        super().__init__()
        self._source = ""
        self._plain = plain

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(2, 2, 2, 2)
        self._layout.setSpacing(8)
        self._children: list[QWidget] = []
        self._prose_widgets: list[QTextBrowser] = []

        self.set_markdown(source)

    # ----------------------------------------------------------------- content

    def markdown(self) -> str:
        return self._source

    def set_markdown(self, source: str) -> None:
        """Replace the rendered content.

        Called on a throttle while an answer streams in, so it must be cheap to
        call repeatedly. Very long documents render as plain text while
        streaming to avoid re-parsing megabytes of markdown on every tick.
        """
        if source == self._source:
            return
        self._source = source
        self._render()

    def set_plain(self, plain: bool) -> None:
        if plain == self._plain:
            return
        self._plain = plain
        self._render()

    def _render(self) -> None:
        for child in self._children:
            self._layout.removeWidget(child)
            child.setParent(None)
            child.deleteLater()
        self._children = []
        self._prose_widgets = []

        if not self._source:
            return

        if self._plain or len(self._source) > self.MAX_LIVE_RENDER_CHARS:
            self._add_prose(self._source, as_plain=True)
            return

        segments = split_segments(self._source)
        for kind, language, text in segments:
            if kind == "code":
                if not text.strip():
                    continue
                widget = CodeBlockWidget(text, language)
            else:
                if not text.strip():
                    continue
                widget = self._prose_widget(text)
            self._children.append(widget)
            self._layout.addWidget(widget)

    def _add_prose(self, text: str, *, as_plain: bool = False) -> None:
        widget = self._prose_widget(text, as_plain=as_plain)
        self._children.append(widget)
        self._layout.addWidget(widget)

    def _refit_children(self) -> None:
        for browser in list(self._prose_widgets):
            try:
                self._fit_height(browser)
            except RuntimeError:
                self._prose_widgets.remove(browser)

    def _prose_widget(self, text: str, *, as_plain: bool = False) -> QWidget:
        colors = _palette()
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setFrameShape(QTextBrowser.NoFrame)
        browser.setStyleSheet(
            f"QTextBrowser {{ background: transparent; border: none;"
            f" color: {colors['text']}; font-size: 13px; }}"
        )
        if as_plain:
            browser.setPlainText(text)
        else:
            html = render_markdown(text)
            html = html.replace("<a ", f'<a style="color:{colors["link"]}" ')
            browser.setHtml(html)
        browser.document().setDocumentMargin(2)
        browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        browser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._prose_widgets.append(browser)
        self._fit_height(browser)
        return browser

    @staticmethod
    def _fit_height(browser) -> None:
        """Grow a prose view to its content so it does not scroll internally."""
        document = browser.document()
        document.setTextWidth(max(200, browser.viewport().width()))
        height = int(document.size().height()) + 10
        browser.setMinimumHeight(max(22, height))
        browser.setMaximumHeight(max(22, height))

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Re-fit prose blocks so text is never clipped after a window resize."""
        super().resizeEvent(event)
        for browser in list(self._prose_widgets):
            try:
                self._fit_height(browser)
            except RuntimeError:
                # The widget was already destroyed by a re-render.
                self._prose_widgets.remove(browser)
        # The first layout pass happens after construction; re-fit once laid out.
        QTimer.singleShot(0, self._refit_children)
