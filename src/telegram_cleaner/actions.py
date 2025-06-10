from enum import Enum

import inquirer
from pyrogram.enums import ChatType
from pyrogram.types import Chat

from telegram_cleaner.translations import _


class Action(str, Enum):
    """All supported user actions."""

    EXPORT_MESSAGES = "action_export_messages"
    EXPORT_REACTIONS = "action_export_reactions"
    DELETE_MESSAGES = "action_delete_messages"
    DELETE_REACTIONS = "action_delete_reactions"
    LEAVE_GROUP = "action_leave_group"
    DELETE_PRIVATE_SELF = "action_delete_private_self"
    DELETE_PRIVATE_BOTH = "action_delete_private_both"


class ActionPicker:
    @staticmethod
    def pick(chats: list[Chat]) -> list[Action]:
        available = ActionPicker.get_available_actions(chats=chats)
        answer = (
            inquirer.prompt(
                [
                    inquirer.Checkbox(
                        "actions",
                        message=_("pick_actions"),
                        choices=[(_(a.value), a) for a in available],
                        carousel=True,
                    )
                ]
            )
            or {}
        )
        return answer.get("actions", [])

    @staticmethod
    def get_available_actions(chats: list[Chat]) -> list[Action]:
        have_private = any(chat.type == ChatType.PRIVATE for chat in chats)
        have_groups = any(
            c.type in (ChatType.GROUP, ChatType.SUPERGROUP) for c in chats
        )

        actions: list[Action] = [
            Action.EXPORT_REACTIONS,
            Action.EXPORT_MESSAGES,
            Action.DELETE_REACTIONS,
            Action.DELETE_MESSAGES,
        ]
        if have_groups:
            actions.append(Action.LEAVE_GROUP)
        if have_private:
            actions.extend([Action.DELETE_PRIVATE_SELF, Action.DELETE_PRIVATE_BOTH])
        return actions
