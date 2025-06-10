import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Sequence

import inquirer
from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.errors import FloodWait, RPCError
from pyrogram.errors.exceptions.bad_request_400 import PeerIdInvalid
from pyrogram.types import Chat
from rich.console import Console
from rich.panel import Panel
from rich.progress import (BarColumn, Progress, ProgressColumn, SpinnerColumn,
                           TextColumn, TimeElapsedColumn)
from rich.prompt import Confirm
from rich.text import Text

from telegram_cleaner.actions import Action, ActionPicker
from telegram_cleaner.config import get_config
from telegram_cleaner.constants import EXPORT_DIR, REACTION_EPOCH
from telegram_cleaner.export import ExportBuffer
from telegram_cleaner.formatting import Formatter
from telegram_cleaner.logging_setup import logging_configure
from telegram_cleaner.translations import _

logging_configure()


class DynamicTextColumn(ProgressColumn):
    def render(self, task):
        if task.total is None:
            return Text(f"{task.completed}/*", style="progress.download")
        return Text(f"{task.completed}/{task.total}", style="progress.download")


class Cleaner:
    CHUNK = 100  # Telegram limit for single delete call

    def __init__(self) -> None:
        cfg = get_config()
        self.lang = cfg.LANG
        self.client = Client("cleaner_session", cfg.API_ID, cfg.API_HASH)
        self.console = Console()
        self.formatter = Formatter
        self.export_buffer = ExportBuffer(console=self.console)
        self.actions_picker = ActionPicker
        self.start_time: str | None = None
        # message-ids from exports (chat_id -> [msg_id, …])
        self.reaction_ids: Dict[int, List[int]] = {}
        self.message_ids: Dict[int, List[int]] = {}

    async def _pick_chats(self) -> list[Chat]:
        dialogs = [
            d.chat
            async for d in self.client.get_dialogs()
            if d.chat.type in (ChatType.PRIVATE, ChatType.GROUP, ChatType.SUPERGROUP)
        ]

        if not dialogs:
            self.console.print(f"[red]{_('no_dialogs')}[/red]")
            return []

        choices = [(f"{c.title or c.first_name} ({c.id})", c.id) for c in dialogs]
        answer = (
            inquirer.prompt(
                [
                    inquirer.Checkbox(
                        "chats",
                        message=_("pick_chats"),
                        choices=choices,
                        carousel=True,
                    )
                ]
            )
            or {}
        )
        picked_ids: List[int] = answer.get("chats", [])
        return [c for c in dialogs if c.id in picked_ids]

    async def _export_messages(self, chat, progress: Progress):
        task = progress.add_task(
            f"[blue]{_('export_messages_progress')} {self.formatter.format_chat_name(chat)}",
            total=None,
        )
        count = 0
        async for msg in self.client.search_messages(chat_id=chat.id, from_user="me"):
            self.export_buffer.add(
                Action.EXPORT_MESSAGES, self.formatter.format_export_line(chat, msg)
            )
            self.message_ids.setdefault(chat.id, []).append(msg.id)
            count += 1
            if count % 100 == 0:
                self.export_buffer.flush()
                progress.update(task, completed=count)
        self.export_buffer.flush()
        progress.update(
            task,
            description=f"[green]{_('export_messages_done')} {self.formatter.format_chat_name(chat)}",
            completed=count,
            total=count,
        )

    async def _export_reactions(self, chat, progress: Progress):
        task = progress.add_task(
            f"[blue]{_('export_reactions_progress')} {self.formatter.format_chat_name(chat)}",
            total=None,
        )
        scanned = 0
        exported = 0
        async for msg in self.client.get_chat_history(chat.id):
            scanned += 1
            if (
                msg.reactions
                and msg.date.replace(tzinfo=timezone.utc) >= REACTION_EPOCH
                and any(r.chosen_order is not None for r in msg.reactions.reactions)
            ):
                exported += 1
                self.reaction_ids.setdefault(chat.id, []).append(msg.id)
                self.export_buffer.add(
                    Action.EXPORT_REACTIONS,
                    self.formatter.format_export_line(chat, msg),
                )
            if msg.date.replace(tzinfo=timezone.utc) < REACTION_EPOCH:
                break
            if scanned % 200 == 0:
                progress.update(task, completed=scanned)
                self.export_buffer.flush()
        self.export_buffer.flush()
        progress.update(
            task,
            description=f"[green]{_('export_reactions_done')} {self.formatter.format_chat_name(chat)}",
            completed=exported,
            total=exported,
        )

    async def _delete_messages(self, chat, progress: Progress):
        ids = self.message_ids.get(chat.id)
        if not ids:
            ids = [
                m.id
                async for m in self.client.search_messages(
                    chat_id=chat.id, from_user="me"
                )
            ]
        total = len(ids)
        task = progress.add_task(
            f"[yellow]{_('deleting_messages_progress', count=total)} {self.formatter.format_chat_name(chat)}",
            total=total or 1,
        )
        for i in range(0, total, self.CHUNK):
            chunk = ids[i : i + self.CHUNK]
            await self.client.delete_messages(chat.id, chunk)
            progress.update(task, advance=len(chunk))
            await asyncio.sleep(0.3)  # small pause to reduce FloodWait
        final_descr = (
            f"[green]{_('messages_done')} {self.formatter.format_chat_name(chat)}"
            if total
            else f"[green]{_('no_messages')} {self.formatter.format_chat_name(chat)}"
        )
        progress.update(task, description=final_descr)

    async def _delete_reactions(self, chat, progress: Progress):
        # if we have ids from export stage
        ids = self.reaction_ids.get(chat.id)
        if ids:
            total = len(ids)
            task = progress.add_task(
                f"[yellow]{_('scan_reactions')} {self.formatter.format_chat_name(chat)}",
                total=total,
            )
            for i, mid in enumerate(ids, 1):
                await self._send_with_retry(
                    self.client.send_reaction,
                    chat.id,
                    mid,
                    "",
                )
                if i % 30 == 0:
                    progress.update(task, completed=i)
            progress.update(
                task,
                description=f"[green]{_('reactions_done')} {self.formatter.format_chat_name(chat)}",
                completed=total,
                total=total,
            )
            return

        task = progress.add_task(
            f"[yellow]{_('scan_reactions')} {self.formatter.format_chat_name(chat)}",
            total=None,
        )
        processed = 0
        removed = 0
        async for msg in self.client.get_chat_history(chat.id):
            if (
                msg.reactions
                and msg.date.replace(tzinfo=timezone.utc) >= REACTION_EPOCH
                and any(r.chosen_order is not None for r in msg.reactions.reactions)
            ):
                await self._send_with_retry(
                    self.client.send_reaction,
                    chat.id,
                    msg.id,
                    "",
                )
                removed += 1
            processed += 1
            if msg.date.replace(tzinfo=timezone.utc) < REACTION_EPOCH:
                break
            if processed and processed % 100 == 0:
                progress.update(task, completed=processed)
                await asyncio.sleep(0.1)
        progress.update(
            task,
            description=f"[green]{_('reactions_done')} {self.formatter.format_chat_name(chat)}",
            completed=removed,
            total=removed,
        )

    async def _process_chat(
        self, chat, actions: Sequence[Action], progress: Progress
    ) -> None:
        if Action.EXPORT_REACTIONS in actions:
            await self._export_reactions(chat, progress)

        if Action.EXPORT_MESSAGES in actions:
            await self._export_messages(chat, progress)

        if Action.DELETE_REACTIONS in actions:
            await self._delete_reactions(chat, progress)

        if Action.DELETE_MESSAGES in actions:
            await self._delete_messages(chat, progress)

    async def _perform_final_actions(self, chat, actions: Sequence[Action]) -> None:
        if (
            chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)
            and Action.LEAVE_GROUP in actions
        ):
            await self.client.leave_chat(chat.id)
            self.console.print(
                f"[cyan]{_('left_chat')} {self.formatter.format_chat_name(chat)}[/cyan]"
            )

        if chat.type == ChatType.PRIVATE:
            if Action.DELETE_PRIVATE_BOTH in actions:
                await self.client.delete_messages(
                    chat_id=chat.id,
                    message_ids=[
                        message.id
                        async for message in self.client.get_chat_history(chat.id)
                    ],
                    revoke=True,
                )
                self.console.print(
                    f"[cyan]{_('deleted_private_both')} {self.formatter.format_chat_name(chat)}[/cyan]"
                )
            elif Action.DELETE_PRIVATE_SELF in actions:
                await self.client.leave_chat(chat.id, delete=True)
                self.console.print(
                    f"[cyan]{_('deleted_private_self')} {self.formatter.format_chat_name(chat)}[/cyan]"
                )

    async def run(self):
        self.console.print(Panel(_("title"), style="bold blue"))

        chats = await self._pick_chats()
        if not chats:
            self.console.print(f"[yellow]{_('nothing_chosen_chats')}[/yellow]")
            return

        actions = self.actions_picker.pick(chats=chats)
        if not actions:
            self.console.print(f"[yellow]{_('nothing_chosen_actions')}[/yellow]")
            return

        self.console.print(f"\n[bold]{_('chosen_chats')}[/bold]")
        for c in chats:
            self.console.print(f" • {self.formatter.format_chat_name(c)}")
        self.console.print(f"\n[bold]{_('actions')}[/bold]")
        for a in actions:
            self.console.print(f" • {_(a.value)}")

        if not Confirm.ask(f"[red]{_('continue')}[/red]", default=False):
            self.console.print(f"[yellow]{_('cancelled')}[/yellow]")
            return

        # parallel processing
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DynamicTextColumn(),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            await asyncio.gather(
                *(self._process_chat(c, actions, progress) for c in chats)
            )

        # sequential final steps
        for chat in chats:
            await self._perform_final_actions(chat, actions)

        self.export_buffer.flush()
        self.console.print(f"\n[bold green]{_('completed')}[/bold green]")

    async def _send_with_retry(self, func, *args, **kwargs):
        while True:
            try:
                return await func(*args, **kwargs)
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except PeerIdInvalid as e:
                self.console.print(
                    f"[red] peer_id_invalid: {e} Args: {args}, Kwargs: {kwargs} [/red]"
                )
                return
            except RPCError as e:
                self.console.print(f"[red]{e}[/red]")
                raise e
            except Exception as e:
                self.console.print(f"[red]{e} Args: {args}, Kwargs: {kwargs}[/red]")
                raise e

    async def __aenter__(self):
        await self.client.start()
        return self

    async def __aexit__(self, *_):
        await self.client.stop()


async def main() -> None:
    try:
        async with Cleaner() as cleaner:
            await cleaner.run()
    except KeyboardInterrupt:
        Console().print(f"\n[yellow]{_('interrupted')}[/yellow]")


if __name__ == "__main__":
    asyncio.run(main())
