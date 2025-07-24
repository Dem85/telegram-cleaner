from datetime import datetime
from typing import Dict, List

from telethon.tl.types import Message
from telethon.utils import get_display_name

from telegram_cleaner.actions import Action
from telegram_cleaner.constants import EXPORT_DIR, ChatEntity


class ExportBuffer:
    def __init__(self, flush_every: int = 100) -> None:
        self._buf: Dict[Action, List[str]] = {a: [] for a in Action}
        self._file_name: str | None = None
        # self._console = console
        self._flush_every = flush_every

    def add(self, action: Action, chat, msg) -> None:
        line = self.format_line(msg=msg, chat=chat)
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

            # if mode == "w":
            #     self._console.print(f"[green]{_('file_saved')}[/green] {path}")
            self._buf[action].clear()

    def flush_needed(self) -> bool:
        return len(self._buf) >= self._flush_every

    def format_line(self, msg: Message, chat: ChatEntity) -> str:
        txt = msg.text or ""
        message_preview = txt.replace("\n", " ")
        ts = msg.date.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{ts}] {get_display_name(chat)} | id={msg.id} | {message_preview}"
