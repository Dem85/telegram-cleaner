"""AI Agent for analyzing messages against Russian legislation.

Supports two providers:
- Ollama (local LLM)
- OpenAI (cloud API, also compatible with any OpenAI-like API)

Features batch processing: multiple messages are sent in a single LLM call
to reduce API costs (one request per batch instead of per-message).

Supports vision analysis: when media (photo) is provided alongside text,
the image is sent to a multimodal LLM for content analysis.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable



import httpx
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()

SYSTEM_PROMPT = """Ты — юридический анализатор текста и изображений. Твоя задача — проверить, содержит ли переданное сообщение (текст и/или изображение) признаки нарушения российского законодательства.

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

Если к сообщению приложено изображение — проанализируй и его содержимое.
Обращай внимание на изображения, которые могут содержать:
- Нацистскую или экстремистскую символику (ст. 20.3 КоАП РФ, ст. 282 УК РФ)
- Призывы к противоправным действиям на плакатах, скриншотах
- Дискредитацию ВС РФ на изображениях (ст. 280.3 УК РФ)

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

Анализируй только содержимое сообщения. Не добавляй отсебятину. Будь консервативен — отмечай только явные нарушения."""

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
class MediaData:
    """Media content for AI vision analysis.

    Attributes:
        data: Raw bytes of the media file.
        mime_type: MIME type (e.g. 'image/jpeg', 'image/png').
    """

    data: bytes
    mime_type: str


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
    timeout: int = 120
    max_retries: int = 3
    # Batch processing
    batch_size: int = 100
    # Vision (image analysis)
    vision_enabled: bool = True
    max_image_size: int = 10 * 1024 * 1024  # 10 MB max image size
    # Retry on 429 Too Many Requests
    max_retries_on_429: int = 5  # additional retries beyond OpenAI client's built-in
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

    async def _call_with_retry_on_429(
        self,
        coro_factory: Callable[[], Any],
        context: str = "",
    ) -> Any:
        """Call an LLM coroutine with retry logic for 429 Too Many Requests.

        The OpenAI client has its own built-in retry (max_retries), but it may
        exhaust them if the rate limit reset time is longer than the client's
        backoff. This method adds an additional layer of retry on top, using
        the ``Retry-After`` or ``retry-after-ms`` headers from the response.

        Args:
            coro_factory: A zero-argument callable that returns an awaitable
                (typically a partial or lambda wrapping an LLM call).
            context: Optional description for log messages (e.g. "batch", "vision").

        Raises:
            httpx.HTTPStatusError: If all retries are exhausted.
        """
        max_retries = self.config.max_retries_on_429
        last_exc: Exception | None = None

        for attempt in range(max_retries):
            try:
                coro = coro_factory()
                if asyncio.iscoroutine(coro):
                    return await coro
                msg = f"coro_factory did not return a coroutine, got {type(coro)}"
                raise TypeError(msg)
            except httpx.HTTPStatusError as e:
                last_exc = e
                if e.response.status_code != 429:
                    raise  # Not a rate-limit error, re-raise immediately

                # Extract retry-after duration from response headers
                retry_after_ms = e.response.headers.get("retry-after-ms")
                retry_after = e.response.headers.get("Retry-After")

                if retry_after_ms is not None:
                    try:
                        wait_time = float(retry_after_ms) / 1000.0
                    except (ValueError, TypeError):
                        wait_time = 5.0
                elif retry_after is not None:
                    try:
                        wait_time = float(retry_after)
                    except (ValueError, TypeError):
                        wait_time = 5.0
                else:
                    wait_time = 5.0

                # Add a small buffer (10%) to be safe
                wait_time *= 1.1

                if attempt < max_retries - 1:
                    logger.warning(
                        "429 Too Many Requests%s — retrying in %.1fs (attempt %d/%d)",
                        f" ({context})" if context else "",
                        wait_time,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        "429 Too Many Requests%s — all %d retries exhausted",
                        f" ({context})" if context else "",
                        max_retries,
                    )
                    raise

        # Should not reach here, but just in case
        if last_exc is not None:
            raise last_exc
        msg = "Unexpected: _call_with_retry_on_429 completed without result or exception"
        raise RuntimeError(msg)

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
            logger.debug("AI DEBUG: Request\n%s", text)
            console.print("[bold yellow]━━━ AI DEBUG: Request ━━━[/bold yellow]")
            console.print(text)
            console.print("[bold yellow]━━━━━━━━━━━━━━━━━━━━━━━━[/bold yellow]")

        try:
            response = await self._call_llm(text)

            if self.config.ai_debug:
                logger.debug("AI DEBUG: Response\n%s", response)
                console.print("[bold cyan]━━━ AI DEBUG: Response ━━━[/bold cyan]")
                console.print(response)
                console.print("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]")

            return self._parse_response(response)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.error(
                    "AI analysis failed for message: 429 Too Many Requests "
                    "(all %d retries exhausted)",
                    self.config.max_retries_on_429,
                )
            else:
                logger.warning(
                    "AI analysis failed for message: HTTP %d %s",
                    e.response.status_code,
                    e.response.reason_phrase,
                )
            return AIAnalysisResult(is_violation=False, confidence=0.0)
        except Exception as e:
            logger.warning("AI analysis failed for message: %s", e)
            return AIAnalysisResult(is_violation=False, confidence=0.0)

    async def analyze_with_media(
        self,
        text: str,
        media: MediaData | None = None,
    ) -> AIAnalysisResult:
        """Analyze a message with optional image content via vision API.

        If media is provided and vision is enabled, the image is sent
        alongside the text to a multimodal LLM.

        Args:
            text: The message text to analyze.
            media: Optional image data for vision analysis.

        Returns:
            AIAnalysisResult with violation detection results.
        """
        if not text and not media:
            return AIAnalysisResult(is_violation=False, confidence=0.0)

        await self._ensure_initialized()

        if self.config.ai_debug:
            logger.debug("AI DEBUG: Request (with media)\n%s", text or "(no text)")
            console.print("[bold yellow]━━━ AI DEBUG: Request (with media) ━━━[/bold yellow]")
            console.print(text or "(no text)")
            if media:
                console.print(f"[dim]Media: {len(media.data)} bytes, {media.mime_type}[/dim]")
            console.print("[bold yellow]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold yellow]")

        try:
            if media and self.config.vision_enabled:
                response = await self._call_llm_with_media(text, media)
            else:
                response = await self._call_llm(text or "")

            if self.config.ai_debug:
                logger.debug("AI DEBUG: Response\n%s", response)
                console.print("[bold cyan]━━━ AI DEBUG: Response ━━━[/bold cyan]")
                console.print(response)
                console.print("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]")

            return self._parse_response(response)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.error(
                    "AI analysis with media failed: 429 Too Many Requests "
                    "(all %d retries exhausted)",
                    self.config.max_retries_on_429,
                )
            else:
                logger.warning(
                    "AI analysis with media failed: HTTP %d %s",
                    e.response.status_code,
                    e.response.reason_phrase,
                )
            return AIAnalysisResult(is_violation=False, confidence=0.0)
        except Exception as e:
            logger.warning("AI analysis with media failed for message: %s", e)
            return AIAnalysisResult(is_violation=False, confidence=0.0)

    async def _call_llm(self, text: str) -> str:
        """Call the LLM and return raw response text."""
        from openai import NOT_GIVEN

        async def _do_call() -> Any:
            return await self._client.chat.completions.create(
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

        completion = await self._call_with_retry_on_429(
            _do_call,
            context="single text",
        )
        return completion.choices[0].message.content or ""

    async def _call_llm_with_media(self, text: str, media: MediaData) -> str:
        """Call the LLM with text and an image for vision analysis.

        Builds a multimodal message with the image encoded as base64 data URL.
        Works with both Ollama (vision models like llava, minicpm-v) and
        OpenAI (gpt-4o, gpt-4o-mini with vision support).
        """
        from openai import NOT_GIVEN

        # Encode image as base64 data URL
        image_base64 = base64.b64encode(media.data).decode("utf-8")
        image_data_url = f"data:{media.mime_type};base64,{image_base64}"

        # Build multimodal user message
        user_content: list[dict] = [
            {
                "type": "text",
                "text": f"Сообщение для анализа:\n\n{text}" if text else "Проанализируй содержимое изображения.",
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": image_data_url,
                    "detail": "auto",  # Let the model decide detail level
                },
            },
        ]

        async def _do_call() -> Any:
            return await self._client.chat.completions.create(
                model=(
                    self.config.ollama_model
                    if self.config.provider == AIProvider.OLLAMA
                    else self.config.openai_model
                ),
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
                max_tokens=500,
                response_format=({"type": "json_object"} if self.config.provider == AIProvider.OPENAI else NOT_GIVEN),
            )

        completion = await self._call_with_retry_on_429(
            _do_call,
            context="vision",
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
            logger.debug("analyze_texts_batch: empty texts list")
            return []

        await self._ensure_initialized()

        # Filter out empty texts and keep track of original indices
        non_empty: list[tuple[int, str]] = [
            (i, t) for i, t in enumerate(texts) if t and t.strip()
        ]

        logger.debug(
            "analyze_texts_batch: %d total texts, %d non-empty",
            len(texts),
            len(non_empty),
        )

        # Pre-fill results for empty texts
        results: list[AIAnalysisResult] = [
            AIAnalysisResult(is_violation=False, confidence=0.0)
            for _ in texts
        ]

        if not non_empty:
            logger.debug("analyze_texts_batch: all texts are empty, returning defaults")
            if progress_callback:
                progress_callback(len(texts), len(texts))
            return results

        # Build the batch payload as a JSON array
        batch_payload = json.dumps(
            [{"id": idx, "text": text} for idx, text in non_empty],
            ensure_ascii=False,
        )

        logger.debug(
            "Sending batch request to LLM: %d messages, payload_size=%d bytes",
            len(non_empty),
            len(batch_payload),
        )

        if self.config.ai_debug:
            logger.debug("AI DEBUG: Batch Request (%d msgs, payload_size=%d bytes)", len(non_empty), len(batch_payload))
            console.print(f"[bold yellow]━━━ AI DEBUG: Batch Request ({len(non_empty)} msgs) ━━━[/bold yellow]")
            console.print(batch_payload[:2000] + ("..." if len(batch_payload) > 2000 else ""))
            console.print("[bold yellow]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold yellow]")

        try:
            raw_response = await self._call_llm_batch(batch_payload)

            logger.debug(
                "Received batch response from LLM: response_size=%d bytes",
                len(raw_response),
            )

            if self.config.ai_debug:
                logger.debug("AI DEBUG: Batch Response (size=%d bytes)", len(raw_response))
                console.print("[bold cyan]━━━ AI DEBUG: Batch Response ━━━[/bold cyan]")
                console.print(raw_response[:2000] + ("..." if len(raw_response) > 2000 else ""))
                console.print("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]")

            parsed = self._parse_batch_response(raw_response)

            logger.debug(
                "Parsed batch response: %d results",
                len(parsed),
            )

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
            # Results for non-empty texts remain as default (is_violation=False)
            # Note: 429 errors are handled by _call_with_retry_on_429 inside _call_llm_batch,
            # so if we get here it's a non-retryable error.

        if progress_callback:
            progress_callback(len(texts), len(texts))

        return results

    async def _call_llm_batch(self, batch_payload: str) -> str:
        """Call the LLM with a batch of messages and return raw response."""
        from openai import NOT_GIVEN

        # Estimate max_tokens: ~100 tokens per message + buffer
        estimated_tokens = max(500, len(json.loads(batch_payload)) * 120)

        async def _do_call() -> Any:
            return await self._client.chat.completions.create(
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

        completion = await self._call_with_retry_on_429(
            _do_call,
            context="batch",
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
        logger.debug(
            "AIAgent.analyze_batch called: %d texts, batch_size=%d",
            len(texts),
            self.config.batch_size,
        )

        if self.config.batch_size <= 1:
            # Legacy mode: one call per message
            results: list[AIAnalysisResult] = []
            total = len(texts)
            for i, text in enumerate(texts):
                logger.debug(
                    "Sending single message to LLM: text_len=%d, text_preview=%s",
                    len(text),
                    text[:100],
                )
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
            logger.debug(
                "Sending chunk to LLM: chunk_start=%d, chunk_size=%d",
                chunk_start,
                len(chunk),
            )
            chunk_results = await self.analyze_texts_batch(
                texts=chunk,
                progress_callback=None,  # We handle progress at chunk level
            )
            all_results.extend(chunk_results)
            if progress_callback:
                progress_callback(min(chunk_start + len(chunk), total), total)

        logger.debug(
            "AIAgent.analyze_batch completed: %d results",
            len(all_results),
        )

        return all_results