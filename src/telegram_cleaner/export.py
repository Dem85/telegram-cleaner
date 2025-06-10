from datetime import datetime
from typing import Dict, List

from telegram_cleaner.actions import Action
from telegram_cleaner.constants import EXPORT_DIR
from telegram_cleaner.translations import _


class ExportBuffer:
    def __init__(self, console) -> None:
        self._buf: Dict[Action, List[str]] = {a: [] for a in Action}
        self._file_name: str | None = None
        self._console = console

    def add(self, action: Action, line: str) -> None:
        self._buf[action].append(line)

    def flush(self) -> None:
        if not self._file_name:
            self._file_name = datetime.now().strftime("%Y%m%d-%H%M%S")

        for action, lines in self._buf.items():
            if not lines:
                continue
            path = EXPORT_DIR / f"{action.name.lower()}_{self._file_name}.txt"
            mode = "a" if path.exists() else "w"
            with open(path, mode, encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")

            if mode == "w":
                self._console.print(f"[green]{_('file_saved')}[/green] {path}")
            self._buf[action].clear()
