class Formatter:
    @staticmethod
    def format_chat_name(chat) -> str:
        return chat.title or f"{chat.first_name} {chat.last_name or ''}".strip()

    @staticmethod
    def format_message_preview(message) -> str:
        txt = message.text or message.caption or ""
        return txt.replace("\n", " ")[:200]

    @staticmethod
    def format_export_line(chat, msg) -> str:
        ts = msg.date.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{ts}] {Formatter.format_chat_name(chat)} | id={msg.id} | {Formatter.format_message_preview(msg)}"
