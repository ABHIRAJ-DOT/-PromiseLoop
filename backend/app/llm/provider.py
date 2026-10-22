"""LLM provider abstraction.

Two providers ship with PromiseLoop:

* ``openai`` - any OpenAI-compatible ``/chat/completions`` endpoint (OpenAI,
  Amazon Bedrock, Groq, OpenRouter, Ollama, ...). Configured with
  ``LLM_BASE_URL`` / ``LLM_API_KEY`` / ``LLM_MODEL``.
* ``mock``   - a deterministic, offline planner. No API key, no network, and
  the same tool-calling loop, so the whole demo (including MCP) works without
  credentials.

Both speak the same message format as the OpenAI chat API, so the agent code
never has to care which one is in use.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.config import get_settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(Protocol):
    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> LLMResponse: ...

    async def structured(
        self, messages: list[dict[str, Any]], schema: dict[str, Any], name: str = "result"
    ) -> dict[str, Any]: ...


class OpenAICompatibleProvider:
    """Talks to any OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.2,
        timeout: float = 45.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions", headers=self._headers(), json=payload
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"LLM request failed ({response.status_code}): {response.text[:500]}"
                )
            return response.json()

    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        data = await self._post(payload)
        message = (data.get("choices") or [{}])[0].get("message") or {}
        calls = [
            ToolCall(
                id=call.get("id", f"call_{index}"),
                name=(call.get("function") or {}).get("name", ""),
                arguments=_safe_json((call.get("function") or {}).get("arguments")),
            )
            for index, call in enumerate(message.get("tool_calls") or [])
        ]
        return LLMResponse(content=message.get("content"), tool_calls=calls)

    async def structured(
        self, messages: list[dict[str, Any]], schema: dict[str, Any], name: str = "result"
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": name, "schema": schema, "strict": True},
            },
        }
        try:
            data = await self._post(payload)
        except RuntimeError:
            # Endpoints without json_schema support still accept json_object.
            payload["response_format"] = {"type": "json_object"}
            data = await self._post(payload)

        content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or "{}"
        return json.loads(content)


def _safe_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_provider() -> LLMProvider:
    """Return the configured provider."""
    settings = get_settings()
    if settings.llm_provider.lower() == "openai":
        return OpenAICompatibleProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
        )
    from app.llm.mock import MockProvider

    return MockProvider()
