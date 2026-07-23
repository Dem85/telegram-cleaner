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
    AI_DEBUG: bool = field(default=False)
    AI_BATCH_SIZE: int = field(default=100)
    AI_TIMEOUT: int = field(default=120)
    # Vision (image analysis) settings
    AI_VISION_ENABLED: bool = field(default=True)
    AI_MAX_IMAGE_SIZE: int = field(default=10 * 1024 * 1024)  # 10 MB
    # Related messages deletion settings
    AI_RELATED_MINUTES: int = field(default=60)
    # Proxy settings
    MTPROTO_ENABLED: bool = field(default=False)
    MTPROTO_TYPE: str = field(default="socks5")
    MTPROTO_HOST: str = field(default="")
    MTPROTO_PORT: int = field(default=0)
    MTPROTO_USER: str = field(default="")
    MTPROTO_PASS: str = field(default="")
    MTPROTO_SECRET: str = field(default="")

    def __post_init__(self) -> None:
        if not isinstance(self.API_ID, int):
            raise ValueError("API_ID must be int")
        if not isinstance(self.API_HASH, str):
            raise ValueError("API_HASH must be str")
        if self.LANG not in ["en", "ru"]:
            raise ValueError(f"unknown language: {self.LANG}")
        if self.AI_PROVIDER not in ("ollama", "openai"):
            raise ValueError(f"unknown AI provider: {self.AI_PROVIDER}")
        if self.MTPROTO_TYPE not in ("socks5", "http", "mtproto"):
            raise ValueError(f"unknown proxy type: {self.MTPROTO_TYPE}")
        if self.MTPROTO_ENABLED and not self.MTPROTO_HOST:
            raise ValueError("MTPROTO_HOST must be set when proxy is enabled")
        if self.MTPROTO_ENABLED and self.MTPROTO_PORT <= 0:
            raise ValueError("MTPROTO_PORT must be > 0 when proxy is enabled")

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
        use_proxy = Prompt.ask(
            "Use proxy?" if lang == "en" else "Использовать прокси?",
            choices=["y", "n"],
            default="n",
        )
        if use_proxy == "y":
            proxy_type = Prompt.ask(
                "Proxy type" if lang == "en" else "Тип прокси",
                choices=["socks5", "http", "mtproto"],
                default="socks5",
            )
            proxy_host = Prompt.ask(
                "Proxy host" if lang == "en" else "Хост прокси",
            )
            proxy_port = int(Prompt.ask(
                "Proxy port" if lang == "en" else "Порт прокси",
            ))
            proxy_secret = ""
            if proxy_type == "mtproto":
                proxy_secret = Prompt.ask(
                    "MTProto secret (hex)" if lang == "en" else "MTProto секрет (hex)",
                )
            cfg = cls(
                API_ID=api_id, API_HASH=api_hash, LANG=lang,
                MTPROTO_ENABLED=True,
                MTPROTO_TYPE=proxy_type,
                MTPROTO_HOST=proxy_host,
                MTPROTO_PORT=proxy_port,
                MTPROTO_SECRET=proxy_secret,
            )
        else:
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
