from __future__ import annotations

from contextlib import asynccontextmanager

import inquirer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Confirm
from rich.text import Text
from telethon.utils import get_display_name

from telegram_cleaner.actions import Action
from telegram_cleaner.constants import ChatEntity
from telegram_cleaner.message_processor import MessageProcessor
from telegram_cleaner.translations import Translator


class DynamicTextColumn(ProgressColumn):
    def render(self, task):
        if task.total is None:
            return Text(f"{task.completed}/*", style="progress.download")
        return Text(f"{task.completed}/{task.total}", style="progress.download")


class InquirerTheme(inquirer.themes.Default):
    def __init__(self):
        super().__init__()
        self.Question.brackets_color = inquirer.themes.term.deepskyblue2
        self.Checkbox.selection_color = inquirer.themes.term.green
        self.Checkbox.selection_icon = "❯"
        self.Checkbox.selected_icon = "◉ "
        self.Checkbox.selected_color = inquirer.themes.term.dodgerblue
        self.Checkbox.unselected_icon = "◯ "
        self.List.selection_color = inquirer.themes.term.bold_black_on_bright_green
        self.List.selection_cursor = "❯"


class TerminalUI:
    def __init__(self, console: Console, translator: Translator) -> None:
        self.console = console
        self.translate = translator

    def show_title(self):
        self.console.print(Panel(self.translate("title"), style="bold blue"))

    def show_completed(self):
        self.console.print(f"\n[bold green]{self.translate('completed')}[/bold green]")

    def pick_chats(self, chats: list[ChatEntity]) -> list[ChatEntity]:
        if not chats:
            self.console.print(f"[red]{self.translate('no_dialogs')}[/red]")
            return []

        choices = [(f"{get_display_name(chat)}", chat.id) for chat in chats]

        answer = (
            inquirer.prompt(
                [
                    inquirer.Checkbox(
                        "chats",
                        message=self.translate("pick_chats"),
                        choices=choices,
                        carousel=True,
                    )
                ],
                theme=InquirerTheme(),
            )
            or {}
        )
        picked_ids: list[int] = answer.get("chats", [])

        if not picked_ids:
            self.console.print(
                f"[yellow]{self.translate('nothing_chosen_chats')}[/yellow]"
            )
        return [chat for chat in chats if chat.id in picked_ids]

    def pick_actions(self, available_actions: list[Action]) -> list[Action]:
        answer = (
            inquirer.prompt(
                [
                    inquirer.Checkbox(
                        "actions",
                        message=self.translate("pick_actions"),
                        choices=[
                            (self.translate(a.value), a) for a in available_actions
                        ],
                        carousel=True,
                    )
                ],
                theme=InquirerTheme(),
            )
            or {}
        )
        actions = answer.get("actions", [])
        if not actions:
            self.console.print(
                f"[yellow]{self.translate('nothing_chosen_actions')}[/yellow]"
            )
        return actions

    def show_resume_info_and_continue(
        self, picked_chats: list[ChatEntity], picked_actions: list[Action]
    ) -> bool:
        self.console.print(f"\n[bold]{self.translate('chosen_chats')}[/bold]")
        for chat in picked_chats:
            self.console.print(f" • {get_display_name(chat)}")
        self.console.print(f"\n[bold]{self.translate('actions')}[/bold]")
        for action in picked_actions:
            self.console.print(f" • {self.translate(action.value)}")
        confirmation = Confirm.ask(
            f"[red]{self.translate('continue')}[/red]", default=False
        )
        if not confirmation:
            self.console.print(f"[yellow]{self.translate('cancelled')}[/yellow]")
        return confirmation

    @asynccontextmanager
    async def progress_context_manager(self):
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DynamicTextColumn(),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            yield progress

    async def scan(self, processor: MessageProcessor, progress) -> None:
        description = f"{self.translate(processor.action.value)}: {get_display_name(processor.chat)}"
        task = progress.add_task(description, total=None)
        processed = 0

        async for msg in processor.async_messages_iterator:
            to_continue = await processor.process(msg=msg)
            if not to_continue:
                break
            processed += 1

            progress.update(task, completed=processed)

        await processor.finalize()
        if processed:
            progress.update(task, completed=processed, total=processed)
        else:
            progress.update(task, completed=1, total=1)
