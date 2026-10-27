# AUDIT_REPORT.md — Qwen Desktop Chat

Independent audit and repair pass. Every claim below is backed by a command that was
actually run, and the raw evidence is quoted.

- **Audit date:** 2026-10-27
- **Workspace:** `C:\Users\Ngo Nhat Nguyen\Desktop\Qwen window build`
- **Git:** **not** a git repository (`git status` → `fatal: not a git repository`), so no
  commits or checkpoints were possible. All changes are plain file edits.
- **Environment:** Windows 10.0.26200, Python 3.14.7 (venv), PySide6 6.12.0

---

## 1. Verdict on the incoming state

The project was **not runnable**. It was not "mostly complete with minor gaps": the entry
point could not be parsed, the GUI could not be constructed, and the service layer called
database methods that do not exist.

Two prior reports (`OVERNIGHT_REPORT.md`) claimed a working state: *"Result: 41 passed"*
and *"the app is structured as an entry point plus separated modules"*. Both claims were
inaccurate as delivered. Measured reality at the start of this audit:

```
$ venv/Scripts/python.exe -m pytest tests/ -q
16 failed, 51 passed
```

```
$ venv/Scripts/python.exe -m pyflakes app main.py tests
main.py:38:42: invalid syntax
    repository = ChatRepository()        credentials = CredentialsManager()
app\ui\chat_view.py:113:38: undefined name 'SSEND_BTN'
app\ui\chat_view.py:121:38: undefined name 'STOP_BTN'
app\ui\chat_view.py:137:47: undefined name 'QStyle'
app\ui\chat_view.py:221:36: undefined name 'COPY_BTN'
app\ui\markdown_widget.py:61:38: undefined name 'QSizePolicy'
app\ui\markdown_widget.py:90:43: undefined name '_wrap_code_block'
```

Final measured state:

```
$ venv/Scripts/python.exe -m pytest tests/ -q
160 passed, 24 subtests passed in 7.88s

$ venv/Scripts/python.exe -m pyflakes app main.py
(no undefined names)
```

---

## 2. P0 — defects that made the application impossible to run

### P0-1 `main.py` was not valid Python

Two statements on one line with no separator, plus indentation errors and imports at
column 0 inside a function body:

```python
    repository = ChatRepository()        credentials = CredentialsManager()
        client = QwenApiClient(...)          # over-indented
...
            if error:
            chat_view.add_error_block(...)   # wrong indent
...
        from app.workers.infer import build_worker, AbortEvent
from app.handlers import build_request_handle, build_retry_worker
```

`pyflakes` reported `main.py:38:42: invalid syntax`. **Nothing** in the app could start.

### P0-2 `markdown_widget.py` imported a symbol that does not exist

```python
from PySide6.QtGui import QPainter, QTextCursor, QTextHtmlFormat, QFont
```

`QTextHtmlFormat` is not part of PySide6 (the class does not exist in Qt). This raised
`ImportError` at import time, so any module importing the markdown widget failed.

### P0-3 `chat_view.py` referenced four undefined names and a non-existent method

- `SSEND_BTN`, `STOP_BTN`, `COPY_BTN` were used to set button styles but never defined.
- `QStyle` was used (`QApplication.style().standardIcon(QStyle.SP_MessageBoxQuestion)`)
  but never imported.
- The message area was a `QTextBrowser` and messages were added with
  `self._messages_widget.addWidget(widget)` — **`QTextBrowser` has no `addWidget`**; it is a
  document widget, not a layout container. The first rendered message would raise
  `AttributeError`.

### P0-4 `sidebar.py` called a helper that does not exist

```python
logo_btn.setIcon(self._icon("house"))
```

`_icon` is never defined anywhere in the class or module. Three calls
(`"house"`, `"chevron_left"`, `"cross"`) → `AttributeError` during `Sidebar.__init__`,
so the main window could not be built.

### P0-5 The service layer called repository methods that do not exist

`app/services/conversation.py` called:

| Called by the service | Exists in `ChatRepository`? |
|---|---|
| `save_conversation(...)` | **No** (the real method is `create_conversation`) |
| `get_conversation_info(...)` | **No** (the real method is `get_conversation`) |
| `save_assistant_started(...)` | **No** |

Sending the first message would have raised `AttributeError`. `main.py` also called
`service.new_conversation(system_prompt=...)` and `service.close_active()`, neither of
which the service accepted or defined.

### P0-6 The worker was not runnable by Qt and called an undefined method

`app/workers/infer.py`:

- Called `self._emit_aborted()` in **six** places; the method is **never defined**.
- Was a plain object started via `QThreadPool.globalInstance().start(worker)`.
  `QThreadPool.start()` requires a `QRunnable`; a plain object raises `TypeError`.
- Exposed `WorkerSignals.chunk` as a **method**, while `main.py` called
  `worker.signals.chunk.connect(...)`, i.e. treating it as a Qt signal.

### P0-7 `keyring` was missing from `requirements.txt` → the API key was silently volatile

`discover_backends()` imports `keyring`; it was not a declared dependency, so it was never
installed. Only the in-memory backend remained, and that backend reported
`is_available = True`.

Consequences, both serious:

1. **Security:** the UI told the user the key had been saved, but it existed only in RAM.
2. **Correctness:** on the next launch `get_key()` returned `None` and the user was
   silently disconnected, with no explanation.

This defeated the stated product requirement to use Windows Credential Manager.

### P0-8 The launcher and README pointed at the wrong things

- `run.bat` looked for `.venv\Scripts\pythonw.exe`; the actual environment folder is `venv`.
  It therefore always printed *"Virtual environment not found. Run setup.bat first."*
  `setup.bat` created `.venv`, so the two scripts disagreed permanently.
- `README.md` instructed `venv\Scripts\pythonw.exe -m app.main` — there is **no**
  `app/main.py`. The correct command is `venv\Scripts\pythonw.exe main.py`.

This is the direct cause of "the app will not start".

---

## 3. P1 — functional defects

### P1-1 Wrong HTTP status extraction hid authentication errors

```python
status_from_exc = getattr(exception, "status_code", None)
```

`urllib.error.HTTPError` exposes `.code`, not `.status_code`. `status_from_exc` was
therefore always `None` and the branch fell through to `return NetworkError()`.
**A wrong API key was reported to the user as a network problem.** The same wrong attribute
was read in `connect_api_dialog._run_test` and `_save`.

### P1-2 The connection test crashed on success

```python
result = client.test_connection()      # returned None
...
model_list = ", ".join(result.get("models", [])[:12])   # AttributeError on None
```

The happy path was the broken one: a *successful* connection raised `AttributeError`.

### P1-3 No streaming client existed

`QwenApiClient` had only a non-streaming `create_chat_completion`. The worker performed its
own `urlopen` and re-implemented parsing, and `CompletionRequest._parse_delta` returned a
`dict` while the caller did `chunk.content` — an attribute that a dict does not have.

### P1-4 The worker issued the HTTP request twice and leaked the first response

```python
def run(self):
    response = self._post()        # request #1
    ...
    chunks = list(self._stream(response))   # ignores `response`

def _stream(self):
    for raw in self.request._iter_lines(self._post()):   # request #2
```

`_stream()` accepted no response and re-posted. Every message was sent twice (double
billing, double side effects) and the first response object was never closed.

### P1-5 Cancellation did not cancel anything

Stop only set a boolean checked between already-buffered lines; the socket was never
closed. The requirement — *"Khi bấm Stop, request phải được hủy ở tầng network"* — was not met.

### P1-6 The connect dialog was never shown

```python
def on_connect() -> None:
    dialog = connect_dialog_factory()
    dialog.finished.connect(update_sidebar)
    # no dialog.exec()
```

The **Connect Qwen API** button did nothing visible. Additionally, `Sidebar._request_connect`
emitted `toggle_requested`, so the button's only real effect was to collapse the sidebar.

### P1-7 The sidebar's Settings button was dead, and the UI crashed on dataclasses

- `settings_btn` was created, given a stylesheet, added to the layout, and **never connected**.
- `set_conversations()` did `c.get("id")` while `service.list_recent()` returned
  `ConversationInfo` dataclasses → `AttributeError`.

### P1-8 Custom model IDs were silently ignored

`SettingsDialog._current_model()` returned `self._model_combo.currentText()` first. Because
the combo always contains the default models, a user typing a custom ID had it replaced by
the first list entry. The stated requirement — *"Có thể cho phép người dùng nhập model ID
thủ công"* — did not work.

### P1-9 Tables never rendered

`_html_safe()` escaped the source and then replaced every newline with `<br>` **before**
calling `markdown()`. Markdown tables require real newlines between rows, so tables (an
explicit requirement) could not work. Pygments was imported but never used, so there was no
syntax highlighting either.

### P1-10 The connection test blocked the UI thread

`_test()` and `_save()` called `client.test_connection()` — a blocking network call —
directly in the Qt slot. This violates the explicit rule *"Không được gọi API đồng bộ trên
UI thread"*.

### P1-11 Other confirmed defects

| Area | Defect |
|---|---|
| `tokens` | `temperature = 0.0` (a valid, deterministic value) was coerced to `0.7` on reload, so the setting silently reverted |
| Search | `search_conversations()` matched only `title` and `id`, never message text — "search history" did not search history |
| Retry | `retry_last_message` did not exist; `app/handlers.py` referenced it anyway |
| Assistant persistence | No code path ever wrote streamed text to the database, so answers vanished on restart |
| Empty placeholder | The empty assistant row was included in the API payload |
| MainWindow | `toggle_theme()` was `pass`; `_open_settings` duplicated `show_settings`; menu actions connected to sidebar attributes that the controller overwrote later |

---

## 4. P2 — structure and maintainability

| Finding | Evidence | Action |
|---|---|---|
| **Two competing state machines** | `app/services/state.py` (string states, used) and `app/conversation/state_machine.py` (Enum states) | Verified `app.conversation` was imported by **nothing** (`grep -rn "app\.conversation"` → only self-references); deleted the module and its folder |
| **`app/handlers.py` was a broken wrapper layer** | Referenced `service.retry_last_message` (absent) and `signals.done.connect` (not a signal); its `build_worker` mutated `client._abort_event` | Deleted; replaced by `app/controller.py`, a real main-thread `QObject` controller |
| **`main.py` held ~270 lines of behaviour** | Violates *"main.py chỉ là entry point"* | Reduced to a bootstrap; behaviour moved to the controller |
| **Dead code** | `ConversationInfo`, `FinishResult.finished`, `_coerce_text`, `_inject_styles`, `SecretAlreadyExistsError`, `_KeyringSecretsBackendFallback`, `ChatView._on_context_menu` (no-op), `_on_focus_changed` (no-op), `set_conversation_model` (no-op), `SettingsDialog._sync_model` (no-op), `_old_settings`/`_copy_settings` (unused) | Removed or replaced with working code |
| **Unused dependencies** | `openai`, `markdown-it-py`, `qt-material`, `chardet` — verified absent from all imports (`grep -rn "^import openai\|markdown_it\|qt_material\|chardet"` → no matches) | Removed from `requirements.txt`; added the missing `keyring` |
| **Unused imports** | ~40 across the UI modules | Reduced using pyflakes output |

---

## 5. Threading and data-safety analysis

The original design made UI updates from a worker thread with no synchronisation, and its
signal objects were plain Python callables, so Qt had no receiver to queue against. Chunks
raised no error but raced the UI thread; service state was mutated from two threads.

The repaired design states its contract explicitly:

```
worker thread  →  network I/O only. Never touches the database, the service, or a widget.
main thread    →  controller (QObject) receives queued signals, updates widgets and SQLite.
```

`InferWorker` is a `QRunnable`; `WorkerSignals` is a `QObject` created on the main thread;
the controller is a main-thread `QObject`, so `Qt.AutoConnection` resolves to a queued
connection. Consequences:

- **No cross-thread SQLite access** (a documented source of corruption and lock errors).
- **No cross-thread widget access.**
- A stale request **cannot** write into the active conversation: `ChatController._on_chunk`
  compares `worker.request_id` with the live handle's id and drops mismatches. Covered by
  `tests/test_controller.py::TestStaleRequestIsolation`.

Other safety properties verified by tests: duplicate sends blocked by `_is_busy()`; a
cancelled or failed request **keeps** its partial text; retry does not duplicate the user
message (so it cannot double the cost); history cannot leak between conversations; the
empty assistant placeholder is filtered out of the API payload.

---

## 6. Security review

Evidence-based conclusions only.

| Question | Verdict | Evidence |
|---|---|---|
| Is the key plaintext in SQLite? | **No** | `app/database/*` never references credentials; only `app/security/*` handles the key |
| Is the key in `settings.json`? | **No** | `AppSettings` has no key field; the settings file stores only preferences |
| Is the key logged? | **No** *(verified by inspection)* | No `logging` call anywhere takes the key; error messages carry only classifier text. `tests/test_api_client.py::TestApiKeyNeverLeaks` asserts a key never appears in error text |
| Can the key reach a third-party server? | **No** | The only outbound host is `client.base_url`, which the user configures |
| Is untrusted model output executed? | **No** | Rendered as rich text only; `QTextBrowser` has no scripting engine. `sanitize_html()` strips `<script>`, `<iframe>`, `<object>`, `<embed>`, `<link>`, `<meta>`, `on*=` handlers and `javascript:` URLs. Covered by `TestSanitize` and `TestRenderMarkdown` |
| Is HTTP (unencrypted) flagged? | **Yes** | Both the connect dialog and Settings warn before accepting a non-loopback `http://` URL |
| Is the key stored in the OS credential store? | **Yes, verified on this machine** | `keyring.get_keyring()` reports `keyring.backends.Windows.WinVaultKeyring`, and `credential.available = True` |

### Verified secure-storage probe

```
$ venv/Scripts/python.exe -c "...discover_backends()..."
  name='Windows Credential Manager'       available=True
  name='in-memory (not persistent)'       available=False
reason: Secure storage is provided by keyring.backends.Windows.
```

The in-memory backend now reports `available = False`, so it can never be mistaken for
durable storage: `CredentialsManager.store_key()` raises instead of pretending to succeed.

### Data integrity

- Every write goes through the `database()` context manager, which commits on success and
  **rolls back on any exception**, so no half-written conversation is possible.
- Import runs inside one transaction, so a malformed payload cannot leave partial data
  (asserted by `test_rejects_malformed_entries_without_partial_write` and
  `test_failed_migration_keeps_existing_data`).
- Import validates the payload version and refuses unknown shapes rather than guessing.
- Migration **refuses** to proceed from an unrecognised schema version instead of
  overwriting data.
- Import is size-limited (64 MB) and content is never executed — only string fields are
  inserted. Imported text renders through the same sanitized markdown path.
- **No test uses the user's real database**: every database test writes to a
  `tempfile.TemporaryDirectory()`. The real database at
  `%USERPROFILE%\.qwen-desktop-chat\` was never opened, modified, or deleted.

---

## 7. Files changed

### Rewritten
| File | Why |
|---|---|
| `main.py` | P0-1; now a thin bootstrap with a visible fatal-error dialog |
| `app/api/errors.py` | P1-1 (`.code`), added `InsufficientQuotaError` usage, safer classification |
| `app/api/client.py` | P1-3, P1-4, P1-5: real streaming, `AbortToken`, correct close handling |
| `app/services/state.py` | Single source of truth; terminal states release resources |
| `app/services/conversation.py` | P0-5: aligned with the real repository; context limiting; title generation; persisted assistant text; retry |
| `app/database/chat_repository.py` | Content search (P1-11); `update_message_content`; `Optional[Path]` typing |
| `app/workers/infer.py` | P0-6: `QRunnable` + real Qt `QObject` signals; single request; token-based cancel |
| `app/ui/markdown_widget.py` | P0-2, P1-9: valid imports, Pygments highlighting, working tables, per-code-block Copy |
| `app/ui/chat_view.py` | P0-3: `QScrollArea` + real container, streaming block updates, working state |
| `app/ui/sidebar.py` | P0-4, P1-6, P1-7: no phantom icons, dedicated signals, context menu |
| `app/ui/main_window.py` | Removed no-op theme toggle; real export/import actions; abort on close |
| `app/ui/connect_api_dialog.py` | P1-1, P1-2, P1-10: correct result handling, prefilled fields, off-thread test |
| `app/ui/settings_dialog.py` | P1-8: custom model precedence; removed dead code; added data management |
| `app/controller.py` | **New** — main-thread `QObject` controller replacing `app/handlers.py` |
| `app/security/secrets_backend.py` | P0-7: honest availability, real keyring probe; error text no longer points at a non-existent `install.bat` |
| `app/security/credentials.py` | P0-7: refuses to save when no secure backend exists |
| `run.bat`, `setup.bat` | P0-8: correct `venv` folder and entry point, logging, verification |
| `requirements.txt` | P0-7 and unused-dependency removal |
| Nine files under `tests/` | Updated to the corrected contracts; 5 new test files added |

### Deleted (with justification)
| Path | Reason |
|---|---|
| `app/conversation/state_machine.py` (+ folder) | Unreferenced duplicate state machine |
| `app/handlers.py` | Broken wrapper layer; superseded by `app/controller.py` |
| `tests/test_handlers_retry.py` | Tested the removed module; replaced by `tests/test_controller.py` |
| `tasks/` | Stray placeholder directory from an earlier session |

---

## 8. What was verified, and how

| Check | Command | Result |
|---|---|---|
| Full test suite | `venv/Scripts/python.exe -m pytest tests/ -q` | **160 passed, 24 subtests passed** |
| Undefined names | `venv/Scripts/python.exe -m pyflakes app main.py` | clean |
| Byte-compilation | `venv/Scripts/python.exe -m compileall -q app main.py` | exit 0 |
| Widget tree, headless | offscreen script building every dialog + window | all 11 checks passed |
| Real bootstrap | `main.main()` with `QApplication.exec` stubbed | returns 0; 1 window "Qwen Desktop Chat" 1280×820 |
| Secure storage | `discover_backends()` on this machine | Windows Credential Manager available |

### Not verified — stated plainly

1. **A real Qwen API call.** No API key was available and none may be invented. The
   streaming path is covered by tests against a fake HTTP response; the live path is not.
2. **On-screen appearance.** This session has no display; all GUI checks used Qt's
   `offscreen` platform. Layout, colours and font rendering have not been seen on a real
   monitor.
3. **The PyInstaller build.** PyInstaller is not installed; `build_exe.bat` is provided but
   was not executed. No `.exe` was produced and none is claimed.
4. **Keyring write on a real interactive Windows session.** Detection is verified; a full
   store/read/delete round trip through Credential Manager was not performed.
