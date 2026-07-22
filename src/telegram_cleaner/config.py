import json
from dataclasses import asdict, dataclass, field

from rich.prompt import Prompt

from telegram_cleaner.ai_agent import AIProvider
from telegram_cleaner.constants import CONFIG_CACHE


@dataclass(slots=True)
class Config:
    API_ID: int
    API_HASH: str
    LANG: str = field(default="en")
    SIMULTANEOUS_PROCESSORS: int = field(default=3)
    # AI settings
    AI_PROVIDER: str = field(default="ollama")
    OLLAMA_URL: str = field(default="http://172.31.240.1:11434")
    OLLAMA_MODEL: str = field(default="llama3.2:3b")
    OPENAI_API_KEY: str = field(default="")
    OPENAI_MODEL: str = field(default="gpt-4o-mini")
    OPENAI_BASE_URL: str = field(default="https://api.openai.com/v1")

    def __post_init__(self) -> None:
        if not isinstance(self.API_ID, int):
            raise ValueError("API_ID must be int")
        if not isinstance(self.API_HASH, str):
            raise ValueError("API_HASH must be str")
        if self.LANG not in ["en", "ru"]:
            raise ValueError(f"unknown language: {self.LANG}")
        if self.AI_PROVIDER not in ("ollama", "openai"):
            raise ValueError(f"unknown AI provider: {self.AI_PROVIDER}")

    def save(self) -> None:
        CONFIG_CACHE.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2))

    @classmethod
    def _ask_user(cls) -> "Config":
        lang = Prompt.ask(
            "Language / Язык",
            choices=["en", "ru"],
            default="en",
        )
        api_id = int(Prompt.ask("Telegram API ID"))
        api_hash = Prompt.ask("Telegram API hash")
        cfg = cls(API_ID=api_id, API_HASH=api_hash, LANG=lang)
        cfg.save()
        return cfg

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_CACHE.exists():
            try:
                return cls(**json.loads(CONFIG_CACHE.read_text()))
            except (ValueError, TypeError, json.JSONDecodeError) as e:
                pass
        return cls._ask_user()
