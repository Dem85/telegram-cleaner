# 🧹 Telegram Cleaner

Telegram Cleaner is a small CLI utility that helps you **keep your Telegram account tidy**.  
With just a few key-strokes you can:

* export or wipe **all your own messages** from any chat (private, group or super-group);
* export or remove **all your reactions** that were added after reactions were introduced (30 Dec 2021);
* **leave groups / super-groups**;
* **delete private dialogues** for yourself or for both participants.

Everything happens in an interactive, colourful TUI that shows live progress bars – so you always
see what is going on.

![](assets/telegram_cleaner_demo.gif)

## ✨ Features

| Category                 | Details                                                                                                      |
|--------------------------|--------------------------------------------------------------------------------------------------------------|
| Export                   | • Your messages to `exports/export_messages_*.txt`  <br>• Your reactions to `exports/export_reactions_*.txt` |
| Bulk deletion            | • Your messages<br>• Your reactions                                                                          |
| Chat actions             | • Leave group / super-group  <br>• Delete private chat (*for me* / *for both*)                               |
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
[YYYY-MM-DD HH:MM:SS] Chat Title | id=123456 | First 200 characters of the message
```

Adjust it easily by editing `Formatter.format_export_line()`.


## 🤖 Under the hood

* **pyrogram** – Telegram API wrapper.
* **rich** – beautiful console output & progress bars.
* **python-inquirer** – interactive check-lists.


## 🧩 Advanced usage

* Add a new language or change the existing one - edit `constants.TRANSLATIONS`.
* Logs can be found in `logs/cleaner.log`.
* This is not recommended, but you can reduce `SAFE_TELEGRAM_WAIT_TIME` to speed up message processing.



## ⚖️ License

MIT © 2025 – feel free to use, modify and share.
