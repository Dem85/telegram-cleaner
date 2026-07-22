"""AI Agent for analyzing messages against Russian legislation.

Supports two providers:
- Ollama (local LLM)
- OpenAI (cloud API, also compatible with any OpenAI-like API)

Features batch processing: multiple messages are sent in a single LLM call
to reduce API costs (one request per batch instead of per-message).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable



from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()

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

BATCH_SYSTEM_PROMPT = """Ты — юридический анализатор текста. Твоя задача — проверить несколько сообщений на признаки нарушения российского законодательства.

Проверяй каждое сообщение по следующим статьям:

1. Ст. 280.3 УК РФ — Дискредитация ВС РФ
2. Ст. 280 УК РФ — Призывы к экстремизму
3. Ст. 319 УК РФ — Оскорбление власти
4. Ст. 207.3 УК РФ — Фейки о военных действиях
5. Ст. 282 УК РФ — Возбуждение ненависти либо вражды
6. Ст. 354.1 УК РФ — Реабилитация нацизма
7. Ст. 20.3 КоАП РФ — Пропаганда нацистской символики
8. Ст. 20.29 КоАП РФ — Экстремистские материалы

Тебе будет передан JSON-массив сообщений в формате:
[{"id": 0, "text": "текст сообщения"}, {"id": 1, "text": "текст сообщения"}, ...]

Для КАЖДОГО сообщения верни результат в том же порядке в формате JSON-массива:
[
  {
    "id": 0,
    "is_violation": true/false,
    "confidence": 0.0-1.0,
    "articles": ["статья_1"],
    "reason": "краткое обоснование на русском языке"
  },
  {
    "id": 1,
    "is_violation": false,
    "confidence": 0.0,
    "articles": [],
    "reason": ""
  }
]

Верни строго JSON-массив. Не добавляй пояснений до или после массива.
Если сообщение пустое — is_violation: false.
Будь консервативен — отмечай только явные нарушения."""


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
    # Batch processing
    batch_size: int = 100
    # Debug
    ai_debug: bool = False


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
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
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
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
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

        if self.config.ai_debug:
            logger.info("=== AI DEBUG: Request ===\n%s", text)
            console.print("[bold yellow]━━━ AI DEBUG: Request ━━━[/bold yellow]")
            console.print(text)
            console.print("[bold yellow]━━━━━━━━━━━━━━━━━━━━━━━━[/bold yellow]")

        try:
            response = await self._call_llm(text)

            if self.config.ai_debug:
                logger.info("=== AI DEBUG: Response ===\n%s", response)
                console.print("[bold cyan]━━━ AI DEBUG: Response ━━━[/bold cyan]")
                console.print(response)
                console.print("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]")

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

    async def analyze_texts_batch(
        self,
        texts: list[str],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[AIAnalysisResult]:
        """Analyze multiple texts in a single LLM call (batch mode).

        Sends all texts as a JSON array in one request. The LLM returns
        a JSON array of results in the same order. This drastically reduces
        API costs compared to calling analyze_text() for each message.

        Args:
            texts: List of message texts to analyze.
            progress_callback: Optional callback with (completed, total).

        Returns:
            List of AIAnalysisResult in the same order as input texts.
        """
        if not texts:
            return []

        await self._ensure_initialized()

        # Filter out empty texts and keep track of original indices
        non_empty: list[tuple[int, str]] = [
            (i, t) for i, t in enumerate(texts) if t and t.strip()
        ]

        # Pre-fill results for empty texts
        results: list[AIAnalysisResult] = [
            AIAnalysisResult(is_violation=False, confidence=0.0)
            for _ in texts
        ]

        if not non_empty:
            if progress_callback:
                progress_callback(len(texts), len(texts))
            return results

        # Build the batch payload as a JSON array
        batch_payload = json.dumps(
            [{"id": idx, "text": text} for idx, text in non_empty],
            ensure_ascii=False,
        )

        if self.config.ai_debug:
            logger.info("=== AI DEBUG: Batch Request (%d msgs) ===\n%s", len(non_empty), batch_payload)
            console.print(f"[bold yellow]━━━ AI DEBUG: Batch Request ({len(non_empty)} msgs) ━━━[/bold yellow]")
            console.print(batch_payload[:2000] + ("..." if len(batch_payload) > 2000 else ""))
            console.print("[bold yellow]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold yellow]")

        try:
            raw_response = await self._call_llm_batch(batch_payload)

            if self.config.ai_debug:
                logger.info("=== AI DEBUG: Batch Response ===\n%s", raw_response)
                console.print("[bold cyan]━━━ AI DEBUG: Batch Response ━━━[/bold cyan]")
                console.print(raw_response[:2000] + ("..." if len(raw_response) > 2000 else ""))
                console.print("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]")

            parsed = self._parse_batch_response(raw_response)

            # Map results back to original positions
            for item in parsed:
                idx = item.get("id")
                if idx is not None and 0 <= idx < len(results):
                    results[idx] = AIAnalysisResult(
                        is_violation=bool(item.get("is_violation", False)),
                        confidence=float(item.get("confidence", 0.0)),
                        articles=list(item.get("articles", [])),
                        reason=str(item.get("reason", "")),
                    )

        except Exception as e:
            logger.warning("Batch AI analysis failed: %s", e)
            # Fall back to individual analysis for each non-empty text
            logger.info("Falling back to individual analysis for %d messages", len(non_empty))
            for orig_idx, text in non_empty:
                results[orig_idx] = await self.analyze_text(text)

        if progress_callback:
            progress_callback(len(texts), len(texts))

        return results

    async def _call_llm_batch(self, batch_payload: str) -> str:
        """Call the LLM with a batch of messages and return raw response."""
        from openai import NOT_GIVEN

        # Estimate max_tokens: ~100 tokens per message + buffer
        estimated_tokens = max(500, len(json.loads(batch_payload)) * 120)

        completion = await self._client.chat.completions.create(
            model=(
                self.config.ollama_model
                if self.config.provider == AIProvider.OLLAMA
                else self.config.openai_model
            ),
            messages=[
                {"role": "system", "content": BATCH_SYSTEM_PROMPT},
                {"role": "user", "content": batch_payload},
            ],
            temperature=0.1,
            max_tokens=estimated_tokens,
            response_format=({"type": "json_object"} if self.config.provider == AIProvider.OPENAI else NOT_GIVEN),
        )
        return completion.choices[0].message.content or ""

    def _parse_batch_response(self, response: str) -> list[dict]:
        """Parse JSON array response from batch LLM call."""
        try:
            # Try to find JSON array in the response
            json_start = response.find("[")
            json_end = response.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                response = response[json_start:json_end]

            data = json.loads(response)
            if isinstance(data, list):
                return data
            # If the model wrapped it in an object (OpenAI json_object mode)
            if isinstance(data, dict):
                # Try common wrapper keys
                for key in ("results", "messages", "data", "response"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
                # If there's only one key and it's a list, use that
                for val in data.values():
                    if isinstance(val, list):
                        return val
            logger.warning(
                "Unexpected batch response format: %s",
                type(data).__name__,
            )
            return []
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(
                "Failed to parse batch AI response: %s | raw: %s",
                e,
                response[:500],
            )
            return []

    async def analyze_batch(
        self,
        texts: list[str],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[AIAnalysisResult]:
        """Analyze a batch of text messages.

        Uses batch mode (single LLM call for all texts) when batch_size > 1.
        Falls back to individual analysis for each text when batch_size == 1.

        Args:
            texts: List of message texts to analyze.
            progress_callback: Optional callback with (completed, total).

        Returns:
            List of AIAnalysisResult in the same order as input texts.
        """
        if self.config.batch_size <= 1:
            # Legacy mode: one call per message
            results: list[AIAnalysisResult] = []
            total = len(texts)
            for i, text in enumerate(texts):
                result = await self.analyze_text(text)
                results.append(result)
                if progress_callback:
                    progress_callback(i + 1, total)
            return results

        # Batch mode: split texts into chunks of batch_size
        all_results: list[AIAnalysisResult] = []
        total = len(texts)

        for chunk_start in range(0, total, self.config.batch_size):
            chunk = texts[chunk_start : chunk_start + self.config.batch_size]
            chunk_results = await self.analyze_texts_batch(
                texts=chunk,
                progress_callback=None,  # We handle progress at chunk level
            )
            all_results.extend(chunk_results)
            if progress_callback:
                progress_callback(min(chunk_start + len(chunk), total), total)

        return all_results