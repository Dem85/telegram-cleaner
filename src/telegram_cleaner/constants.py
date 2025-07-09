from datetime import datetime, timezone
from pathlib import Path
from typing import Union

from telethon.tl.types import Channel, Chat, User

from telegram_cleaner.actions import Action
from telegram_cleaner.message_processor import (
    DeleteChatForBothProcessor,
    DeleteChatOnlyForMeProcessor,
    ExportMessagesProcessor,
    ExportReactionsProcessor,
    LeaveGroupProcessor,
    RemoveMessagesProcessor,
    RemoveReactionsProcessor,
)

# telegram
SAFE_TELEGRAM_WAIT_TIME = 3.5

# typing
ChatEntity = Union[User, Chat, Channel]

# config
CONFIG_CACHE = Path(__file__).with_name("cache.json")

# reactions
REACTION_EPOCH = datetime(
    2021, 12, 30, tzinfo=timezone.utc
)  # when reactions were added to TG

# export
EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(exist_ok=True)

# logging
LOG_DIR = Path("logs")
LOG_PATH = LOG_DIR / "cleaner.log"
LOG_DIR.mkdir(exist_ok=True)

# translations
TRANSLATIONS = {
    "en": {
        # UI
        "title": "🧹 Telegram Cleaner",
        "no_dialogs": "No suitable chats found",
        "pick_chats": "Pick chats",
        "pick_actions": "Pick actions",
        "nothing_chosen_chats": "No chats chosen – exiting",
        "nothing_chosen_actions": "No actions chosen – exiting",
        "chosen_chats": "Chats chosen:",
        "actions": "Actions:",
        "continue": "Continue?",
        "cancelled": "Cancelled",
        "completed": "✅ Completed",
        "interrupted": "Interrupted by user",
        # Progress messages
        "scan_messages": "Scanning messages",
        "scan_reactions": "Scanning reactions",
        "delete_messages": "Deleting",
        "no_messages": "No messages found",
        "messages_done": "Messages processed",
        "reactions_done": "Reactions processed",
        "export_messages_progress": "Exporting messages from",
        "export_messages_done": "Messages export completed for",
        "export_reactions_progress": "Exporting reactions from",
        "export_reactions_done": "Reactions export completed for",
        "deleting_messages_progress": "Deleting {count} messages from",
        # Chat actions
        "left_chat": "Left chat:",
        "deleted_private_both": "Private chat deleted (for both):",
        "deleted_private_self": "Private chat deleted (for me only):",
        # File operations
        "file_saved": "File created:",
        "lines": "lines",
        "message": "Message",
        "reaction": "Reaction",
        # Flood wait
        "flood_wait": "FloodWait: waiting {seconds} seconds...",
        # Actions (for menu)
        "action_delete_messages": "Delete all my messages",
        "action_delete_reactions": "Remove all my reactions",
        "action_export_messages": "Export messages to delete",
        "action_export_reactions": "Export reactions to remove",
        "action_leave_group": "Leave GROUP/SUPERGROUP",
        "action_delete_private_self": "Delete PRIVATE chat (for me only)",
        "action_delete_private_both": "Delete PRIVATE chat (for both)",
        # Config
        "language_prompt": "Language / Язык",
        "api_id_prompt": "Telegram API ID",
        "api_hash_prompt": "Telegram API hash",
    },
    "ru": {
        # UI
        "title": "🧹 Telegram Cleaner",
        "no_dialogs": "Подходящих чатов не найдено",
        "pick_chats": "Выберите чаты",
        "pick_actions": "Выберите действия",
        "nothing_chosen_chats": "Чаты не выбраны – выход",
        "nothing_chosen_actions": "Действия не выбраны – выход",
        "chosen_chats": "Выбранные чаты:",
        "actions": "Действия:",
        "continue": "Продолжить?",
        "cancelled": "Отменено",
        "completed": "✅ Завершено",
        "interrupted": "Прервано пользователем",
        # Progress messages
        "scan_messages": "Сканируем сообщения",
        "scan_reactions": "Сканируем реакции",
        "delete_messages": "Удаляем",
        "no_messages": "Сообщений не найдено",
        "messages_done": "Сообщения удалены",
        "reactions_done": "Реакции сняты",
        "export_messages_progress": "Экспортируем сообщения из",
        "export_messages_done": "Экспорт сообщений завершён для",
        "export_reactions_progress": "Экспортируем реакции из",
        "export_reactions_done": "Экспорт реакций завершён для",
        "deleting_messages_progress": "Удаляем {count} сообщений из",
        # Chat actions
        "left_chat": "Вышли из чата:",
        "deleted_private_both": "Удалён приватный чат (для обоих):",
        "deleted_private_self": "Удалён приватный чат (только для меня):",
        # File operations
        "file_saved": "Создан файл:",
        "lines": "строк",
        "message": "Сообщение",
        "reaction": "Реакция",
        # Flood wait
        "flood_wait": "FloodWait: ожидаем {seconds} секунд...",
        # Actions (for menu)
        "action_delete_messages": "Удалить все свои сообщения",
        "action_delete_reactions": "Снять все свои реакции",
        "action_export_messages": "Выгрузить сообщения на удаление",
        "action_export_reactions": "Выгрузить реакции на снятие",
        "action_leave_group": "Выйти из GROUP/SUPERGROUP",
        "action_delete_private_self": "Удалить PRIVATE только для себя",
        "action_delete_private_both": "Удалить PRIVATE для обоих",
        # Config
        "language_prompt": "Language / Язык",
        "api_id_prompt": "Telegram API ID",
        "api_hash_prompt": "Telegram API hash",
    },
}

ACTION_PROCESSOR_MAPPING = {
    Action.DELETE_MESSAGES: RemoveMessagesProcessor,
    Action.DELETE_REACTIONS: RemoveReactionsProcessor,
    Action.EXPORT_MESSAGES: ExportMessagesProcessor,
    Action.EXPORT_REACTIONS: ExportReactionsProcessor,
    Action.LEAVE_GROUP: LeaveGroupProcessor,
    Action.DELETE_PRIVATE_BOTH: DeleteChatForBothProcessor,
    Action.DELETE_PRIVATE_SELF: DeleteChatOnlyForMeProcessor,
}
