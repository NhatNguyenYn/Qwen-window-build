# TEST_REPORT.md — Qwen Desktop Chat

- **Date:** 2026-10-27
- **Command used for every result below:** `venv\Scripts\python.exe -m pytest tests/ -q`
- **Python:** 3.14.7 (project venv) · **PySide6:** 6.12.0

---

## 1. Headline result

| | Before audit | After repair |
|---|---|---|
| Test suite | **16 failed, 51 passed** | **160 passed, 24 subtests passed, 0 failed** |
| Runtime | 1.05 s | 7.88 s |
| Undefined names (pyflakes) | 7 in app + main.py | 0 |
| `main.py` parseable | **No** (`invalid syntax`) | Yes |
| GUI constructible | **No** | Yes (verified headless) |
| `main()` boot completes | **No** | Yes (window 1280×820) |

A clean run truncates to:

```
........................................................................ [ 45%]
................................................... [ 76%]
.....................................                                 [100%]
160 passed, 24 subtests passed in 7.88s
```

---

## 2. Test files

| File | Tests | What it protects |
|---|---|---|
| `test_api_client.py` | 26 | Request shape, SSE parsing, all HTTP status classes, streaming, abort token, response closing, key never leaking |
| `test_conversation.py` | 29 | Service ↔ repository contract against a **real temp database**, history isolation, retry without duplication, context limiting, partial-content persistence, restart survival |
| `test_controller.py` | 18 | Duplicate-send gating, stale-request isolation, stop, finalize-and-persist once, navigation blocking |
| `test_markdown.py` | 21 | Table/list/heading rendering, code segmentation, XSS sanitizing, theme switching |
| `test_workers_infer.py` | 16 | Success/cancel/failure paths, exactly-one-terminal-signal, `QRunnable` contract |
| `test_request_state.py` | 19 | Every legal and illegal transition, terminal-state resource release |
| `test_database.py` | 8 | CRUD, ordering, cascade delete, idempotent schema init |
| `test_database_migration.py` | 12 | Version guards, transactional import, malformed payload rejection, truncation |
| `test_config.py` | 7 | Defaults, file round trip, corrupt-file fallback, value clamping |
| `test_main_import.py` | 8 (+24 subtests) | Every module imports; widget tree builds offscreen |
| **Total** | **160** | |

Notable regression tests that encode a specific fixed defect:

| Test | Original defect |
|---|---|
| `test_http_error_status_is_read_from_code` | A wrong API key was reported as a *network* error |
| `test_test_connection_reports_count` | A **successful** connection test crashed with `AttributeError` |
| `test_renders_table` | Markdown tables could never render (`nl2br` destroyed row breaks) |
| `test_refresh_sidebar_accepts_repository_rows` | Sidebar crashed on the service's dataclasses (`.get` on an object) |
| `test_history_does_not_leak_across_conversations` | Prompt assembly could mix conversations |
| `test_retry_does_not_duplicate_user_message` | Retry could re-send (and re-bill) the same prompt |
| `test_abort_during_stream_raises_and_closes` | Stop did not close the socket |
| `test_abort_mid_stream` (`test_workers_infer`) | Same, at the worker level |
| `test_stale_chunk_is_ignored` (controller) | A late chunk could land in the wrong conversation |
| `test_partial_answer_is_kept` ×3 (controller) | Failed/cancelled answers were lost |
| `test_messages_survive_a_new_repository_instance` | Answers were never persisted at all |
| `test_every_app_module_imports` | 2 modules could not be imported |
| `test_widget_tree_constructs` | 4 undefined names made the window unbuildable |

---

## 3. Regression matrix

`A` = automated test · `H` = verified headless (offscreen, no display) · `M` = needs manual check

| Area | Case | How | Status |
|---|---|---|---|
| **Startup** | Fresh install, no data | `test_controller_start_populates_empty_state` | A — pass |
| | Missing configuration (no key) | `test_send_without_key_does_not_start_a_worker` | A — pass |
| | New database created | `TestConversationLifecycle` setUp | A — pass |
| | Full bootstrap to visible window | `main()` with exec stubbed | H — pass |
| **API** | Wrong key (401) | `test_auth`, `test_http_error_status_is_read_from_code` | A — pass |
| | Wrong model (404) | `test_model_not_found` | A — pass |
| | Wrong endpoint (DNS/URLError) | `test_connection_error_from_urlerror` | A — pass |
| | Rate limit (429) | `test_rate_limit_is_retryable` | A — pass |
| | Payment (402) | `test_payment` | A — pass |
| | Server error (5xx) | `test_server_error_retryable` | A — pass |
| | Timeout | `test_timeout_from_exception` | A — pass |
| | Unexpected 400 | `test_unexpected_status_is_not_retryable` | A — pass |
| | **Live call to real Qwen** | — | **M — not done, no key available** |
| **Streaming** | Success | `test_yields_deltas` | A — pass |
| | Mid-stream failure | `test_interrupted_stream_raises_network_error` | A — pass |
| | Stop / cancel | `test_abort_during_stream_raises_and_closes`, `test_request_abort_during_stream_emits_cancelled` | A — pass |
| | Socket closed after completion | `test_response_is_closed_after_stream` | A — pass |
| | No duplicate HTTP request | `test_exactly_one_terminal_signal` + single `_post` design | A — pass |
| **Conversation** | Create new | `test_new_conversation_is_persisted_and_active` | A — pass |
| | Rename | `test_rename_and_delete`, `test_rename_rejects_blank` | A — pass |
| | Reopen after restart | `test_messages_survive_a_new_repository_instance` | A — pass |
| | Delete single | `test_rename_and_delete` | A — pass |
| | Delete all | `test_delete_all_removes_everything` | A — pass |
| | Search by message text | `test_search_matches_message_content` | A — pass |
| | Title auto-generated | `test_title_is_generated_from_first_message` | A — pass |
| | History isolation | `test_history_does_not_leak_across_conversations` | A — pass |
| | Context limit | `test_context_limit_is_respected` | A — pass |
| **Database** | Ordering preserved | `test_messages_roundtrip` | A — pass |
| | Cascade delete | `test_delete_cascades_messages` | A — pass |
| | Schema init idempotent | `test_schema_initialization_idempotent` | A — pass |
| | Migration version guard | `test_unknown_previous_version_is_rejected` | A — pass |
| | Failed migration preserves data | `test_failed_migration_keeps_existing_data` | A — pass |
| | Malformed import rejected | `test_rejects_non_object_payload`, `test_rejects_wrong_version` | A — pass |
| | Import is additive | `test_import_does_not_delete_existing_data` | A — pass |
| **UI** | Dark/Light switch | `test_theme_colors_are_applied`, headless theme switch | A + H — pass |
| | Widget tree | `test_widget_tree_constructs` | H — pass |
| | Resize behaviour | `MarkdownWidget.resizeEvent` re-fits prose | **M — visual check needed** |
| | Send/Stop state | `test_send_creates_conversation_and_starts_one_worker`, `test_stop_aborts_worker_and_token` | A — pass |
| | Keyboard shortcuts | Wired in `_build_menu` and `eventFilter` | **M — visual check needed** |
| | Dialog fits on screen | Sizes set (`setMinimumSize`) | **M — visual check needed** |
| **Security** | Key not in error text | `test_key_absent_from_error_message` | A — pass |
| | Script injection stripped | `TestSanitize` (5 tests), `test_strips_script_from_model_output` | A — pass |
| | HTML in code block escaped | `test_escapes_html_in_code_block` | A — pass |
| | HTTP endpoint warning | Code paths in both dialogs | **M — visual check needed** |
| | Credential store detection | `discover_backends()` | Verified — WinVault available |
| | Full credential round trip | — | **M — not done** |
| **Packaging** | `run.bat` correctness | Fixed to the real `venv` folder | Verified by inspection |
| | `setup.bat` verification step | `import PySide6, keyring, markdown, pygments` | Ran — pass |
| | Data outside the install dir | `%USERPROFILE%\.qwen-desktop-chat` | Verified by inspection |
| | `.exe` build | `build_exe.bat` → PyInstaller one-folder | **Ran — build succeeded, `.exe` produced** |
| | `.exe` actually starts | Launched with an isolated `USERPROFILE` | **N — ran 12 s, no traceback, created `chat.db`, exited cleanly** |
| **Recovery** | Restart keeps history | `test_messages_survive_a_new_repository_instance` | A — pass |
| | Interrupted request keeps partial text | 3 controller tests | A — pass |
| | Settings survive restart | `test_roundtrip_file` | A — pass |
| | Corrupt settings file | `test_corrupt_file_falls_back` | A — pass |

---

## 4. Headless GUI verification (raw output)

Building the complete widget tree on Qt's `offscreen` platform:

```
1. all imports OK
2. repo/service OK
3. sidebar + chat view constructed OK
4. MainWindow constructed OK
5. controller.start() OK
6. new_chat OK, active = 6c477330-... count = 1
7. message rendering OK
8. streaming block OK
9. busy state OK
10. sidebar populated OK, items = 1
11. theme switch OK
ALL GUI CONSTRUCTION CHECKS PASSED
```

Full bootstrap through the real entry point:

```
$ QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe  (main.main() with exec probed, then quit)
main() returned: 0
top-level windows seen INSIDE the event loop: 6
   title=''                    size=100x30    visible=False
   title=''                    size=100x30    visible=False
   title='Qwen Desktop Chat'   size=1280x820  visible=True     <-- the application window
   title=''                    size=100x30    visible=False
   title=''                    size=100x30    visible=False
   title=''                    size=100x30    visible=False
```

The count of six is Qt's own hidden helper windows (100×30, never visible), not extra app
windows. Filtering by visibility leaves **exactly one** window, with the expected title and
geometry. The probe runs *inside* the event loop — a check made after `quit()` would
measure zero windows and prove nothing.

This is strong evidence the window builds and shows, but **it is not a substitute for
looking at the application on a real screen.** No pixel-level or interaction claim is made.

### Packaged executable

The built `.exe` was launched with an isolated `USERPROFILE` (so it could not read or write
the real user data directory) and left running for 12 seconds:

```
$ cd "dist/Qwen Desktop Chat" && USERPROFILE=<temp> ./"Qwen Desktop Chat.exe"
[process alive after 12 s]
[no output on stderr — no traceback]
$ find "$ISOLATED_PROFILE" -name chat.db -exec ls -l {} \;
-rw-r--r-- 40960  .qwen-desktop-chat/chat.db
[terminated cleanly]
```

A build that merely *succeeds* proves nothing about the bundle; this proves the frozen
bundle actually **starts, initialises its database, and does not crash**. It also proves
the app writes data to the user profile rather than into its own install folder, and that
a first launch on a machine with no existing data works.

**Still not verified for the `.exe`:** the window rendering on a real display, the API key
round trip through Windows Credential Manager from inside the frozen bundle, and a live
Qwen request. Run the ten checks in section 5 against the `.exe` if you intend to use it as
your primary route.

---

## 5. Manual checks still required

Run these once on a real desktop session with a real API key:

1. `run.bat` — window appears, no console errors.
2. **Connect Qwen API** → paste key → **Test Connection** → expect green *Connected*.
3. Send a prompt → confirm tokens appear progressively, not all at once.
4. Press **Stop** mid-answer → confirm it stops promptly and the partial text remains.
5. Reload the app → confirm the conversation is still in the sidebar with its answer.
6. Toggle **Settings → Appearance → Light**, press OK → confirm the whole UI changes.
7. Copy a code block → paste into Notepad → confirm the raw code (not HTML) arrives.
8. Send a message with a deliberately wrong key → confirm the message names an
   authentication problem, **not** a network problem.
9. Resize the window narrow → confirm markdown text re-flows instead of being clipped.
10. Close the window while streaming → confirm the app closes without hanging.

---

## 6. Test-suite integrity notes

- No test was deleted or weakened to make the suite pass. Two tests were **rewritten
  because they asserted incorrect behaviour**:
  - `test_failed_keeps_handle` asserted that a failed request retains its abort handle.
    That is wrong: a terminal request cannot be aborted, and holding the handle keeps the
    network response alive. The replacement
    (`test_handle_released_for_every_terminal_state`) asserts release for all three
    terminal states.
  - `test_workers_infer` was rewritten from a plain-callback API to the Qt-signal API
    because the plain-callback contract was the *cause* of the P0 defect (the GUI could
    not connect to it).
- Two test failures encountered during this work were traced to **my own test doubles**,
  not to production code: `FakeClient` did not honour the abort token, and `FakeWorker`
  lacked a `signals` object. Both doubles were corrected to mirror the real contract, and
  the worker additionally gained an up-front cancellation check.
- Every database test uses `tempfile.TemporaryDirectory()`. **Your real database was never
  touched.** The suite creates no files outside temporary directories.
- The suite requires **no API key and makes no network calls**, so it is safe to run
  repeatedly and costs nothing.
