"""AI Agent for analyzing messages against Russian legislation.

Supports two providers:
- Ollama (local LLM)
- OpenAI (cloud API, also compatible with any OpenAI-like API)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — юридический анализатор текста. Твоя задача — проверить, содержит ли переданное сообщение признаки нарушения российского законодательства.

Проверяй сообщение по следующим статьям:

1. Ст. 280.3 УК РФ — Дискредитация ВС РФ
   - Публичные действия, направленные на дискредитацию использования Вооружённых Сил РФ
   - Признаки: негативные высказывания об армии РФ, призывы против военных операций, распространение заведомо ложной информации о действиях ВС РФ

2. Ст. 280 УК РФ — Призывы к экстремизму
   - Публичные призывы к осуществлению экстремистской деятельности
   - Признаки: призывы к насильственному изменению конституционного строя, нарушению территориальной целостности РФ

3. Ст. 319 УК РФ — Оскорбление власти
   - Публичное оскорбление представителя власти при исполнении им своих должностных обязанностей
   - Признаки: унизительные высказывания в адрес государственных служащих, сотрудников правоохранительных органов, судей

4. Ст. 207.3 УК РФ — Фейки о военных действиях
   - Публичное распространение заведомо ложной информации об использовании ВС РФ
   - Признаки: утверждения о событиях, не соответствующие официальным сводкам, неподтверждённые данные о потерях, военных преступлениях

5. Ст. 282 УК РФ — Возбуждение ненависти либо вражды
   - Действия, направленные на возбуждение ненависти либо вражды по признакам пола, расы, национальности, языка, происхождения, отношения к религии
   - Признаки: унизительные высказывания по национальному/религиозному признаку, призывы к дискриминации

6. Ст. 354.1 УК РФ — Реабилитация нацизма
   - Отрицание фактов, установленных приговором Нюрнбергского трибунала, одобрение преступлений нацизма
   - Признаки: оправдание нацизма, отрицание Холокоста, распространение заведомо ложных сведений о деятельности СССР в годы ВОВ

7. Ст. 20.3 КоАП РФ — Пропаганда нацистской символики
   - Публичное демонстрирование нацистской символики или атрибутики
   - Признаки: изображения свастики, символов SS, нацистских приветствий

8. Ст. 20.29 КоАП РФ — Экстремистские материалы
   - Распространение материалов, включённых в федеральный список экстремистских
   - Признаки: ссылки на запрещённые организации, цитирование экстремистской литературы

Ответ верни строго в формате JSON:
{
  "is_violation": true/false,
  "confidence": 0.0-1.0,
  "articles": ["статья_1", "статья_2"],
  "reason": "краткое обоснование на русском языке"
}

Если нарушений нет, верни:
{
  "is_violation": false,
  "confidence": 0.0,
  "articles": [],
  "reason": ""
}

Анализируй только текст сообщения. Не добавляй отсебятину. Будь консервативен — отмечай только явные нарушения."""


class AIProvider(str, Enum):
    """Supported AI providers."""

    OLLAMA = "ollama"
    OPENAI = "openai"


@dataclass(slots=True)
class AIAnalysisResult:
    """Result of AI analysis of a message."""

    is_violation: bool
    confidence: float
    articles: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass(slots=True)
class AIConfig:
    """Configuration for AI provider."""

    provider: AIProvider = AIProvider.OLLAMA
    # Ollama settings
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    # OpenAI settings
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    # Common
    timeout: int = 60
    max_retries: int = 3


class AIAgent:
    """AI agent that analyzes messages against Russian legislation.

    Client is initialized lazily on first use to avoid ImportError
    when the openai package is not installed and no AI actions are selected.
    """

    def __init__(self, config: AIConfig) -> None:
        self.config = config
        self._client: Any = None
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Lazy initialization of the LLM client."""
        if self._initialized:
            return
        self._init_client()
        self._initialized = True

    def _init_client(self) -> None:
        """Initialize the appropriate client based on provider."""
        if self.config.provider == AIProvider.OLLAMA:
            self._init_ollama()
        elif self.config.provider == AIProvider.OPENAI:
            self._init_openai()
        else:
            msg = f"Unknown AI provider: {self.config.provider}"
            raise ValueError(msg)

    def _init_ollama(self) -> None:
        """Initialize Ollama client using openai-compatible endpoint."""
        try:
            from openai import OpenAI as OpenAIClient

            self._client = OpenAIClient(
                base_url=f"{self.config.ollama_url.rstrip('/')}/v1",
                api_key="ollama",  # Ollama doesn't need a real key
                timeout=self.config.timeout,
                max_retries=self.config.max_retries,
            )
            logger.info(
                "Ollama client initialized: url=%s, model=%s",
                self.config.ollama_url,
                self.config.ollama_model,
            )
        except ImportError as e:
            msg = (
                "openai package is not installed. "
                "Install it with: pip install openai\n"
                "Or use the system venv:\n"
                "  source .venv2/bin/activate && pip install openai"
            )
            logger.error(msg)
            raise ImportError(msg) from e

    def _init_openai(self) -> None:
        """Initialize OpenAI client."""
        try:
            from openai import OpenAI as OpenAIClient

            self._client = OpenAIClient(
                api_key=self.config.openai_api_key,
                base_url=self.config.openai_base_url,
                timeout=self.config.timeout,
                max_retries=self.config.max_retries,
            )
            logger.info(
                "OpenAI client initialized: model=%s, base_url=%s",
                self.config.openai_model,
                self.config.openai_base_url,
            )
        except ImportError as e:
            msg = (
                "openai package is not installed. "
                "Install it with: pip install openai\n"
                "Or use the system venv:\n"
                "  source .venv2/bin/activate && pip install openai"
            )
            logger.error(msg)
            raise ImportError(msg) from e

    async def analyze_text(self, text: str) -> AIAnalysisResult:
        """Analyze a single text message for legal violations.

        Args:
            text: The message text to analyze.

        Returns:
            AIAnalysisResult with violation detection results.
        """
        if not text or not text.strip():
            return AIAnalysisResult(is_violation=False, confidence=0.0)

        await self._ensure_initialized()

        try:
            response = await self._call_llm(text)
            return self._parse_response(response)
        except Exception as e:
            logger.warning("AI analysis failed for message: %s", e)
            return AIAnalysisResult(is_violation=False, confidence=0.0)

    async def _call_llm(self, text: str) -> str:
        """Call the LLM and return raw response text."""
        from openai import NOT_GIVEN

        completion = await self._client.chat.completions.create(
            model=(
                self.config.ollama_model
                if self.config.provider == AIProvider.OLLAMA
                else self.config.openai_model
            ),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Сообщение для анализа:\n\n{text}"},
            ],
            temperature=0.1,
            max_tokens=500,
            response_format=({"type": "json_object"} if self.config.provider == AIProvider.OPENAI else NOT_GIVEN),
        )
        return completion.choices[0].message.content or ""

    def _parse_response(self, response: str) -> AIAnalysisResult:
        """Parse JSON response from LLM into AIAnalysisResult."""
        try:
            # Try to find JSON in the response (in case model adds extra text)
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                response = response[json_start:json_end]

            data = json.loads(response)
            return AIAnalysisResult(
                is_violation=bool(data.get("is_violation", False)),
                confidence=float(data.get("confidence", 0.0)),
                articles=list(data.get("articles", [])),
                reason=str(data.get("reason", "")),
            )
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning("Failed to parse AI response: %s | raw: %s", e, response)
            return AIAnalysisResult(is_violation=False, confidence=0.0)

    async def analyze_batch(
        self,
        texts: list[str],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[AIAnalysisResult]:
        """Analyze a batch of text messages.

        Args:
            texts: List of message texts to analyze.
            progress_callback: Optional callback with (completed, total).

        Returns:
            List of AIAnalysisResult in the same order as input texts.
        """
        results: list[AIAnalysisResult] = []
        total = len(texts)

        for i, text in enumerate(texts):
            result = await self.analyze_text(text)
            results.append(result)
            if progress_callback:
                progress_callback(i + 1, total)

        return results