from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from telethon.tl.types import Channel, Chat, User

if TYPE_CHECKING:
    from telegram_cleaner.constants import ChatEntity


class Action(str, Enum):
    """All supported user actions."""

    EXPORT_MESSAGES = "action_export_messages"
    EXPORT_REACTIONS = "action_export_reactions"
    DELETE_MESSAGES = "action_delete_messages"
    DELETE_REACTIONS = "action_delete_reactions"
    LEAVE_GROUP = "action_leave_group"
    DELETE_PRIVATE_BOTH = "action_delete_private_both"
    DELETE_PRIVATE_SELF = "action_delete_private_self"
    # AI-powered actions
    AI_ANALYZE_TEXT = "action_ai_analyze_text"
    AI_ANALYZE_ALL = "action_ai_analyze_all"
    AI_ANALYZE_AND_DELETE_TEXT = "action_ai_analyze_and_delete_text"
    AI_ANALYZE_AND_DELETE_ALL = "action_ai_analyze_and_delete_all"
    # AI-powered actions with related messages deletion
    AI_ANALYZE_AND_DELETE_WITH_RELATED_TEXT = "action_ai_analyze_and_delete_with_related_text"
    AI_ANALYZE_AND_DELETE_WITH_RELATED_ALL = "action_ai_analyze_and_delete_with_related_all"
    # AI: own messages + replies only (no time window)
    AI_ANALYZE_AND_DELETE_OWN_AND_REPLIES_TEXT = "action_ai_analyze_and_delete_own_and_replies_text"
    AI_ANALYZE_AND_DELETE_OWN_AND_REPLIES_ALL = "action_ai_analyze_and_delete_own_and_replies_all"


def get_available_actions(chats: list["ChatEntity"]) -> list[Action]:
    have_private = any(isinstance(chat, User) for chat in chats)
    have_groups = any(isinstance(chat, (Channel, Chat)) for chat in chats)

    actions: list[Action] = [
        Action.EXPORT_REACTIONS,
        Action.EXPORT_MESSAGES,
        Action.DELETE_REACTIONS,
        Action.DELETE_MESSAGES,
    ]
    if have_groups:
        actions.append(Action.LEAVE_GROUP)
    if have_private:
        actions.extend([Action.DELETE_PRIVATE_BOTH, Action.DELETE_PRIVATE_SELF])
    # AI-powered actions are always available
    actions.extend([
        Action.AI_ANALYZE_TEXT,
        Action.AI_ANALYZE_ALL,
        Action.AI_ANALYZE_AND_DELETE_TEXT,
        Action.AI_ANALYZE_AND_DELETE_ALL,
        Action.AI_ANALYZE_AND_DELETE_WITH_RELATED_TEXT,
        Action.AI_ANALYZE_AND_DELETE_WITH_RELATED_ALL,
        Action.AI_ANALYZE_AND_DELETE_OWN_AND_REPLIES_TEXT,
        Action.AI_ANALYZE_AND_DELETE_OWN_AND_REPLIES_ALL,
    ])
    return actions
