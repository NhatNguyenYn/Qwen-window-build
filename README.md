# Qwen Desktop Chat

A desktop chat client for Qwen models, built with Python and PySide6. Local history,
streaming answers, markdown with syntax highlighting, and an API key that lives in the
Windows credential store rather than in a text file.

---

## Quick start (Windows)

### Option A — the built executable (no Python needed)

Run **`dist\Qwen Desktop Chat\Qwen Desktop Chat.exe`**.

Keep the whole folder: the build is one-folder, so the `.exe` will not run on its own.

### Option B — run from source

1. **Set up once** — double-click **`setup.bat`**.
   Creates the `venv` environment and installs dependencies. Wait for
   *“Setup finished successfully.”*

2. **Start the app** — double-click **`run.bat`**.

### Then, either way

3. **Connect your key** — in the app, click **Connect Qwen API** in the left sidebar, paste
   your key, click **Save & Connect**. Then start typing.

If something goes wrong, `run.bat` writes a log to `logs\app.log` and prints the last lines.
For a visible error console, run:

```bat
venv\Scripts\python.exe main.py
```

> The environment already exists in this workspace, so step 1 can be skipped.

**Full instructions (Vietnamese):** see [USER_GUIDE_VI.md](USER_GUIDE_VI.md).

---

## Layout

```
main.py              entry point only — bootstrap and fatal-error reporting
app/
  controller.py      main-thread QObject wiring UI ↔ service ↔ workers
  api/               OpenAI-compatible client, streaming, error classification
  services/          conversation workflow and the request state machine
  database/          SQLite schema, repository, migration, JSON export/import
  security/          API key storage policy and backends
  config/            settings persistence
  workers/           background streaming worker (QRunnable + Qt signals)
  ui/                window, sidebar, chat view, markdown, dialogs
  styles.py          dark/light stylesheet
tests/               160 tests, no network and no API key required
```

Architecture and dependency rules: [ARCHITECTURE.md](ARCHITECTURE.md).
Audit findings and evidence: [AUDIT_REPORT.md](AUDIT_REPORT.md).
Test results and regression matrix: [TEST_REPORT.md](TEST_REPORT.md).

---

## Requirements

- Windows, Python 3.11+ (developed and tested on 3.14.7)
- `PySide6`, `Pygments`, `markdown`, `keyring` (see `requirements.txt`)

`keyring` is required: without it the API key cannot be stored securely, and the app will
refuse to save it rather than write it to disk in plain text.

---

## Qwen API configuration

The app talks to the OpenAI-compatible endpoint:

| Account type | Base URL |
|---|---|
| Mainland China (the default) | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| International | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |

Get a key from Alibaba Cloud Model Studio (DashScope). Default model list:
`qwen-turbo`, `qwen-plus`, `qwen-max`, `qwen-long`, `qwen3-max-latest`,
`qwen3-235b-a22b-instruct-cosmo`.

Model names change over time. Settings → Model → **Custom…** lets you type any model ID
your account can access, so a new release never requires touching the code.

---

## Data and privacy

| What | Where |
|---|---|
| Conversations | `%USERPROFILE%\.qwen-desktop-chat\chat.db` (SQLite) |
| Preferences | `%USERPROFILE%\.qwen-desktop-chat\settings.json` |
| **API key** | **Windows Credential Manager**, entry `QwenDesktopChat` |

The key is never written to the database, the settings file, or any log, and it is only
sent to the endpoint you configure. There is no telemetry. Model output is rendered as
rich text and is never executed.

Use **File → Export history…** for a JSON backup, and **File → Import history…** to restore
one. Import only adds conversations; it never overwrites or deletes.

---

## Running the tests

```bat
venv\Scripts\python.exe -m pytest tests/ -q
```

Expected: **160 passed**. No API key and no network access are needed.

---

## Packaging

A built executable is already present in this workspace:

```
dist\Qwen Desktop Chat\Qwen Desktop Chat.exe
```

To rebuild it after changing code, run **`build_exe.bat`** (it installs PyInstaller if
missing). The build uses PyInstaller in one-folder mode, so the whole
`dist\Qwen Desktop Chat\` directory must be kept together, not just the `.exe`.

This was built and smoke-tested in this workspace: the executable started, stayed alive
with the Qt event loop running, created its `chat.db` in the user data directory, produced
no traceback, and exited cleanly when asked to stop.

The built executable contains no API key, and history stays in
`%USERPROFILE%\.qwen-desktop-chat\`, so rebuilding never touches your conversations.

---

## License and cost

This is a personal desktop client. It bundles no models and no API access. Your API key
and any usage charges are your own responsibility.
