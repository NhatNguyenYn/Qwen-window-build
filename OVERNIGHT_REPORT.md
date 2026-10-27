# OVERNIGHT_REPORT.md — superseded

> **This file has been superseded.** It previously contained status claims that did not
> match the delivered code. It is kept only so the history of the file is not silently
> rewritten; the claims below are **not** valid.

## What this file used to claim

- *"Result: 41 passed"* for the test suite.
- *"`main.py` remains the entry point and stays short."*
- *"Full test run ... 41 passed after fixes."*
- *"Streaming worker uses typed cancellation checks."*

## Why those claims were wrong

A later independent audit measured the actual state of the same workspace:

| Claim | Measured reality |
|---|---|
| 41 tests passing | `16 failed, 51 passed` |
| Entry point works | `main.py:38:42: invalid syntax` — the file could not be parsed at all |
| Streaming worker works | `Worker._emit_aborted()` was called six times and never defined; the worker was not a `QRunnable`, so `QThreadPool.start()` would raise `TypeError` |

The report also stated the GUI had not been run end-to-end, which was accurate — but it
did not state that the GUI **could not** be constructed. It could not: four undefined names
in `chat_view.py`, a missing `_icon` helper in `sidebar.py`, and an import of the
non-existent `QTextHtmlFormat` in `markdown_widget.py`.

## Where the current status lives

- **[AUDIT_REPORT.md](AUDIT_REPORT.md)** — every defect, with the command output that
  demonstrates it, and what was changed.
- **[TEST_REPORT.md](TEST_REPORT.md)** — test results and the full regression matrix,
  including what is explicitly *not* verified.
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — the structure and threading contract as built.
- **[USER_GUIDE_VI.md](USER_GUIDE_VI.md)** — Vietnamese end-user instructions.

Current measured state: **160 passed**, no undefined names, GUI constructible, `main()`
boots to a visible 1280×820 window.
