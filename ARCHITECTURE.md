# ARCHITECTURE.md — Qwen Desktop Chat

Describes the real structure of the codebase as it stands, including the dependency rules
and the threading contract.

---

## 1. Directory tree

```
main.py                      entry point (bootstrap only)
app/
  __init__.py
  controller.py              ChatController(QObject) — the only orchestrator
  styles.py                  dark/light palettes + global stylesheet
  api/
    client.py                QwenApiClient, CompletionRequest, AbortToken, streaming
    errors.py                ApiError hierarchy + classify_error()
  services/
    conversation.py          ConversationService, SendHandle
    state.py                 RequestState, TransitionGuard, InFlightRequest
  database/
    db.py                    connection factory, database() context manager, schema
    chat_repository.py       ChatRepository — all conversation/message SQL
    migration.py             version guard + JSON export/import
  security/
    secrets_backend.py       SecretsBackend ABC, keyring backend, honest probe
    credentials.py           CredentialsManager — storage policy
  config/
    settings.py              AppSettings, load_settings, save_settings
  workers/
    infer.py                 InferWorker(QRunnable), WorkerSignals(QObject)
  ui/
    app.py                   App(QApplication) subclass
    main_window.py           MainWindow — layout and menus only
    sidebar.py               Sidebar — conversation list, emits intent signals
    chat_view.py             ChatView — message area, composer, send/stop
    markdown_widget.py       MarkdownWidget, CodeBlockWidget, rendering
    connect_api_dialog.py    ConnectApiDialog + off-thread connection test
    settings_dialog.py       SettingsDialog
    about_dialog.py          AboutDialog
tests/                       160 tests
```

There is exactly **one** state machine (`app/services/state.py`). A second, unreferenced
Enum-based machine previously existed at `app/conversation/state_machine.py` and was
deleted.

---

## 2. Data flow

### Startup

```
main.main()
  → load_settings()                          config/settings.py
  → set_render_theme() + QApplication stylesheet
  → ChatRepository()                         creates/validates SQLite schema
  → CredentialsManager()                     probes keyring availability
  → ConversationService(repository, client)
  → Sidebar, ChatView, MainWindow
  → ChatController(...)                      main-thread QObject
  → controller.start()                       populate sidebar, open newest conversation
  → window.show(); app.exec()
```

Any exception during this sequence is caught at the bottom of `main.py` and shown in a
message box with the full traceback, rather than failing silently.

### Sending a message

```
ChatView.send_requested(str)
  └─ ChatController.send_message()
       ├─ _require_key()                    no key → visible error block, stop
       ├─ _is_busy()?                       already running → ignore (blocks double-click)
       ├─ ConversationService.send_message()
       │    ├─ repository.append_message(user)         persisted
       │    ├─ repository.generate_initial_title()     first message names the chat
       │    ├─ repository.append_message(assistant,"") placeholder row
       │    └─ build_request()                         system prompt + recent history
       ├─ ChatView.add_user_message()
       ├─ _start_request(handle)
       │    ├─ ChatView.set_busy(True)      Send hidden, Stop shown
       │    ├─ service.mark_streaming()     IDLE → CONNECTING → STREAMING
       │    └─ QThreadPool.start(worker)    ────────────┐
       └─ QTimer(70 ms).start()                          │
                                                         ▼
                                       (worker thread) InferWorker.run()
                                         QwenApiClient.stream_chat_completion()
                                           emits chunk(str) per delta
                                           emits done | failed | cancelled
                                                         │
                       queued signals (main thread)      │
                                                         ▼
       _on_chunk()  → buffer (dropped if request_id is stale)
       _flush_stream() → ChatView.append_streaming()
       _on_done / _on_failed / _on_cancelled → _finalize(state)
         ├─ service.store_assistant_text(message_id, text)   one write
         ├─ service.finish_request(handle, state)
         ├─ ChatView.end_streaming()    empty bubble removed, partial text flagged
         ├─ ChatView.set_busy(False)
         └─ refresh_sidebar()
```

### Database write path

```
ChatRepository method
  → database(path)  (context manager in app/database/db.py)
      sqlite3.connect(isolation_level=DEFERRED, timeout=10)
      PRAGMA journal_mode=WAL, synchronous=NORMAL, foreign_keys=ON
      yield connection
      success → commit()          failure → rollback() and re-raise
```

Every write therefore has transaction semantics. A failed write cannot leave a partially
saved conversation.

---

## 3. Dependency rules

Strictly one direction. The layer below never imports the layer above.

```
ui/  ──►  controller  ──►  services/  ──►  database/
              │                │
              │                └──────────►  api/        (client + errors)
              ├───────────────►  workers/   ──►  api/
              └───────────────►  security/  ──►  (keyring)
                                 config/    ──►  (filesystem only)
```

| Rule | How it is upheld |
|---|---|
| Widgets never run SQL | No `ui/` module imports `database/`. Only the controller touches `ChatRepository` |
| Widgets never build requests | No `ui/` module imports `api/` except for `ApiError` types used in dialogs |
| Widgets never call the network | The only network call sites are `api/client.py` (used by the worker and by the connect dialog's off-thread task) |
| Services never import Qt | `services/`, `database/`, `config/`, `security/`, `api/` contain no Qt import, so they are testable without a display |
| The entry point holds no logic | `main.py` builds objects and calls `controller.start()` |

Verified mechanically: `tests/test_main_import.py::test_every_app_module_imports` plus the
fact that every non-`ui`, non-`controller` test runs without a `QApplication`.

---

## 4. Threading contract

This is the part the original code got wrong, so it is stated explicitly.

| Thread | May do | Must not do |
|---|---|---|
| **Main (GUI) thread** | Touch widgets, open/close SQLite, mutate `ConversationService`, abort a request | Block on network I/O |
| **Worker thread** (`InferWorker.run`) | Perform HTTP I/O, emit Qt signals | Touch widgets, touch the database, mutate the service |

How the contract is enforced:

- `InferWorker` is a `QRunnable`; `WorkerSignals` is a `QObject` constructed on the main
  thread; `ChatController` is a main-thread `QObject`. Qt's `AutoConnection` therefore
  selects a **queued** connection, so worker emissions run as main-thread callbacks.
- `InferWorker` holds only a client, a request, and an `AbortToken` — it has no reference
  to the repository or the service, so it *cannot* violate the rule.
- The connection test inside `ConnectApiDialog` runs in a `_ConnectionTestTask(QRunnable)`
  for the same reason: a blocking call in a dialog slot would freeze the window.

### Cancellation

`AbortToken` keeps a reference to the live HTTP response. `abort()` sets the flag **and
closes the response object**, which unblocks the pending `readline()` in the worker thread.
This is genuine network-level cancellation, not a hidden spinner. `abort()` is safe to call
from the main thread while the worker is blocked. `stop_request()` also calls
`service.cancel_pending()` so the service's view of the request matches the network.

### Stale-request isolation

`ChatController._on_chunk` ignores any chunk whose `worker.request_id` differs from the
live `SendHandle.request_id`. A response that outlives its request can never be written into
the conversation the user is now looking at.

### Streaming throttling

Deltas are buffered and flushed to the widget every 70 ms (`STREAM_FLUSH_MS`) instead of
once per token, which keeps repainting cheap and stops the view flickering during long
answers. The buffer is drained on finalize so no text is lost.

---

## 5. Request state machine

`app/services/state.py` — states `IDLE → CONNECTING → STREAMING → {COMPLETED | CANCELLED | FAILED}`.

```
IDLE        → CONNECTING | COMPLETED | CANCELLED | FAILED
CONNECTING  → STREAMING  | COMPLETED | CANCELLED | FAILED
STREAMING   → COMPLETED  | CANCELLED | FAILED
terminal    → itself only
```

- Any other transition raises `StateTransitionError` immediately; illegal state cannot
  propagate silently.
- Terminal states release the abort handle, including `FAILED`: aborting a finished request
  is meaningless and a retained handle would keep the response object alive. **Retry builds
  a new request with a new handle** rather than resurrecting the old one.
- `InFlightRequest.__post_init__` re-validates a rehydrated state through the guard, so
  constructing an impossible state fails loudly.

---

## 6. Extension points

The structure was kept open for the features listed as out of MVP scope:

| Future feature | Where it plugs in |
|---|---|
| A second AI provider | Add a class with `stream_chat_completion` / `test_connection`; `ConversationService` depends only on that surface. `AppSettings.provider` already exists, and the connect dialog already has a provider combo |
| File upload / vision | Add parts to `CompletionRequest.to_dict()`; nothing else changes |
| Web search tooling | Wrap the client in an `api/` decorator; services and UI are unaffected |
| Conversation export variants | Extend `database/migration.py`; the UI only calls `export_conversations` / `import_conversations` |
| More request states | Extend `RequestState._ALLOWED`; the guard and all callers follow automatically |

---

## 7. Deliberate non-abstractions

Things that were **removed** rather than kept, so the design does not carry dead weight:

- `app/handlers.py` — a module of helper functions that referenced a non-existent service
  method and a non-existent signal API. Replaced by the controller.
- `app/conversation/state_machine.py` — a second state machine nothing imported.
- `ConversationInfo` dataclass — the service now returns plain repository dicts, removing an
  entire conversion layer and a whole class of `.get`-on-object bugs.
- `InMemorySecretsBackend` as a silent fallback — it now reports `is_available = False`, so
  it can never be mistaken for durable storage.
- Aggregator/Factory layers that only forwarded calls to a single collaborator.
