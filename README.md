# 🧹 Telegram Cleaner

Telegram Cleaner is a small CLI utility that helps you **keep your Telegram account tidy**.
With just a few key-strokes you can:

* export or wipe **all your own messages** from any chat (private, group or super-group);
* export or remove **all your reactions** that were added after reactions were introduced (30 Dec 2021);
* **leave groups / super-groups**;
* **delete private dialogues** for yourself or for both participants;
* **AI-powered analysis** of messages for potential violations of Russian legislation;
* **AI-powered deletion** of violating messages (for everyone).

Everything happens in an interactive, colourful TUI that shows live progress bars – so you always
see what is going on.

![](assets/telegram_cleaner_demo.gif)

## ✨ Features

| Category                 | Details                                                                                                      |
|--------------------------|--------------------------------------------------------------------------------------------------------------|
| Export                   | • Your messages to `exports/export_messages_*.txt`  <br>• Your reactions to `exports/export_reactions_*.txt` |
| Bulk deletion            | • Your messages<br>• Your reactions                                                                          |
| Chat actions             | • Leave group / super-group  <br>• Delete private chat (*for me* / *for both*)                               |
| AI analysis              | • Analyze text messages for RU law violations via LLM<br>• Analyze text + media (photo, video, audio)        |
| AI deletion              | • Analyze & delete violating messages (for everyone)                                                         |
| Multi-chat processing    | All chosen chats are processed **in parallel** for maximum speed                                             |
| Safety first             | Provides exports (for debug purposes also) & asks for confirmation before doing anything destructive         |
| Language support         | English & Russian (more can be added easily)                                                                 |
| Cross-platform           | Works anywhere Python 3.12+ runs                                                                             |


## Installation

### 1. Linux / macOS

1. Install **pipx**

```bash
python3 -m pip install --user pipx
```

```bash
pipx ensurepath
```

2. Install **uv**

```bash
pipx install uv
```

3. Create & activate a virtual environment

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

4. Install the package:

Main dependencies only

```bash
uv pip install .
```

Development tools

```bash
uv pip install -e .[dev]
```

Tests (pytest, coverage …)

```bash
uv pip install -e .[test]
```

Development + Tests

```bash
uv pip install -e .[dev,test]
```

### 2. Windows (PowerShell / cmd.exe)

Preliminary check: Ensure Python is installed (version 3.8+ for uv). In your terminal, run python --version. If the command is not found:
- Try py --version (if Python Launcher is available).
- Or use the full path to python.exe (e.g., C:\Python311\python.exe --version).
- If nothing works, add Python to PATH: reinstall Python with the "Add Python to PATH" option or manually configure environment variables.

Next, **depending on which command worked for you**, use `python` / `py` / `full path to python` in terminal. In the instructions, I use `python` for simplicity's sake.

1. Install **pipx**

```bash
python -m pip install --user pipx
```

```bash
pipx ensurepath
```

2. Install **uv**

```bash
pipx install uv
```

3. Create & activate a virtual environment

**Navigate to the project folder**: Before creating the virtual environment and installing the package, change to your project's directory (where the pyproject.toml is located). Use the command `cd path_to_folder` (e.g., `cd C:\Projects\telegram-cleaner`). This is necessary for commands like `uv pip install .` to work correctly relative to the current directory.

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

4. Install the package:

Main dependencies only

```bash
uv pip install .
```

Development tools

```bash
uv pip install -e .[dev]
```

Tests (pytest, coverage …)

```bash
uv pip install -e .[test]
```

Development + Tests

```bash
uv pip install -e .[dev,test]
```



## 🔑 First-time configuration

Telegram Cleaner needs a _user_ API ID / Hash – create them once at
https://my.telegram.org/apps (they are free).

On the **first launch** the program will ask you:

* Interface language: `en` / `ru`
* **API ID**
* **API Hash**

The answers are stored in `src/telegram_cleaner/cache.json`.
You can delete/modify this file at any moment to re-configure the tool.

> **MTProto proxy**: If you need to connect through a proxy, add the corresponding
> fields to `cache.json` manually (see [Advanced usage](#-advanced-usage)).


## ▶️ Usage

From the project folder, execute the command:

```bash
python -m telegram_cleaner.main
```

Step-by-step flow:

1. Pick one or many chats from the list.
2. Pick actions to perform.
3. Review chosen chats & actions, press **Y** to continue or **N** to abort.
4. Watch pretty progress bars do their magic 🙂
5. A final “✅ Completed” will appear and, if you exported data, you will find new
    files in the `exports/` folder.

### Export file format

Each line is plain text:

```
[YYYY-MM-DD HH:MM:SS] Chat Title | id=123456 | Message text
```

Adjust it easily by editing `ExportBuffer.format_line()`.


## 🤖 Under the hood

* **pyrogram** – Telegram API wrapper.
* **rich** – beautiful console output & progress bars.
* **python-inquirer** – interactive check-lists.
* **openai** – LLM client for AI analysis (works with both OpenAI API and Ollama).


## 🧠 AI-powered analysis

Telegram Cleaner can analyze your messages using a Large Language Model (LLM) to detect
potential violations of Russian legislation. Two providers are supported:

### Ollama (local, default)

Run the LLM on your own machine — no data leaves your network.

```bash
# Install Ollama: https://ollama.ai
ollama pull llama3.2:3b
```

Default configuration (auto-detected):
- `AI_PROVIDER=ollama`
- `OLLAMA_URL=http://172.31.240.1:11434`
- `OLLAMA_MODEL=llama3.2:3b`

### OpenAI (cloud)

Uses OpenAI API or any OpenAI-compatible API.

```bash
# Get API key from https://platform.openai.com
```

Configure in `cache.json`:
- `AI_PROVIDER=openai`
- `OPENAI_API_KEY=sk-...`
- `OPENAI_MODEL=gpt-4o-mini`

### Available AI actions

When you select chats, the following AI-powered actions appear in the menu:

| Action | Description |
|--------|-------------|
| **AI: Analyze text for RU law violations** | Scans all text messages and reports which ones may violate Russian legislation |
| **AI: Analyze text, photos, videos, audio for RU law violations** | Same as above, but also includes media messages (caption text is analyzed) |
| **AI: Analyze text & DELETE (for everyone) if violation found** | Analyzes text messages and automatically deletes violating ones with `revoke=True` |
| **AI: Analyze all media & DELETE (for everyone) if violation found** | Analyzes all messages including media and deletes violating ones for everyone |

### How it works

1. All messages are collected during the scan phase
2. Messages are sent to the LLM in **batches** (default: 100 messages per request) — this drastically reduces API costs
3. The LLM receives a JSON array of messages and returns a JSON array of results in one response
4. If a violation is detected, the message is flagged (and optionally deleted)
5. The analysis is conservative — only clear violations are reported

> **Note:** The system prompt and full list of checked articles are in [`RUSSIAN_LAWS.md`](RUSSIAN_LAWS.md).

### Batch processing (cost optimization)

Instead of sending one API request per message (which would duplicate the system prompt each time),
Telegram Cleaner **collects all messages and sends them in a single LLM call**.

| Setting | Default | Description |
|---------|---------|-------------|
| `AI_BATCH_SIZE` | `100` | Number of messages per LLM request. Set to `1` to disable batching (legacy mode). |

**How much does this save?**

- Without batching: N API calls for N messages, each with a full system prompt
- With batching (`batch_size=100`): 1 API call per 100 messages
- For 1000 messages: **1000 calls → 10 calls** (100× reduction in API calls)
- System prompt is sent once instead of 1000 times

Configure in `cache.json`:

```json
{
  "AI_BATCH_SIZE": 100
}
```

> **Note:** For Ollama (local LLM), batching also speeds up analysis significantly since
> the model processes multiple texts in a single inference pass.


## 🧩 Advanced usage

* Add a new language or change the existing one - edit `constants.TRANSLATIONS`.
* Logs can be found in `logs/cleaner.log`.
* This is not recommended, but you can reduce `SAFE_TELEGRAM_WAIT_TIME` to speed up message processing.

### Proxy (SOCKS5 / HTTP / MTProto)

If your network requires a proxy to connect to Telegram, you can configure it in
`cache.json`:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `MTPROTO_ENABLED` | `bool` | `false` | Set to `true` to enable the proxy |
| `MTPROTO_TYPE` | `str` | `"socks5"` | Proxy type: `"socks5"`, `"http"`, or `"mtproto"` |
| `MTPROTO_HOST` | `str` | `""` | Proxy hostname or IP address |
| `MTPROTO_PORT` | `int` | `0` | Proxy port |
| `MTPROTO_USER` | `str` | `""` | Proxy username (optional, SOCKS5/HTTP only) |
| `MTPROTO_PASS` | `str` | `""` | Proxy password (optional, SOCKS5/HTTP only) |
| `MTPROTO_SECRET` | `str` | `""` | MTProto proxy secret (required when `MTPROTO_TYPE=mtproto`) |

#### SOCKS5 / HTTP examples

SOCKS5 with authentication:

```json
{
  "MTPROTO_ENABLED": true,
  "MTPROTO_TYPE": "socks5",
  "MTPROTO_HOST": "127.0.0.1",
  "MTPROTO_PORT": 1080,
  "MTPROTO_USER": "user",
  "MTPROTO_PASS": "password"
}
```

HTTP proxy without authentication:

```json
{
  "MTPROTO_ENABLED": true,
  "MTPROTO_TYPE": "http",
  "MTPROTO_HOST": "192.168.1.1",
  "MTPROTO_PORT": 8080
}
```

#### MTProto proxy

For MTProto proxy you need to provide the **secret** (usually a hex string or
a base64-encoded string that may start with `ee` for fake-TLS mode):

```json
{
  "MTPROTO_ENABLED": true,
  "MTPROTO_TYPE": "mtproto",
  "MTPROTO_HOST": "proxy.example.com",
  "MTPROTO_PORT": 443,
  "MTPROTO_SECRET": "ee000000000000000000000000000000"
}
```

> **Note:** When `MTPROTO_TYPE=mtproto`, the program automatically uses
> `ConnectionTcpMTProxyRandomizedIntermediate` as the connection type and
> passes `(host, port, secret)` to `TelegramClient(proxy=...)`.
> `MTPROTO_USER` and `MTPROTO_PASS` are ignored for MTProto proxies.



## ⚖️ License

MIT © 2025 – feel free to use, modify and share.
