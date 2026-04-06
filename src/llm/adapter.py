"""
LLM adapter — typed interface for MiniMax, OpenAI, and Anthropic chat completions.

Mirrors the adapter pattern used elsewhere: swap provider via LLM_PROVIDER config.
All providers implement the same interface so agent code is provider-agnostic.

Design:
- ChatCompletion: send a messages array, receive a typed response
- Function calling: pass function schemas to the model; receive tool_call in response
- Streaming: return an async generator for token-by-token streaming
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator, Coroutine, Literal

import httpx

from src.config import get_settings


# ─── Message types ─────────────────────────────────────────────────────────────

@dataclass
class Message:
    """A single message in a chat conversation."""
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = None


@dataclass
class ToolCall:
    """A tool call requested by the model."""
    id: str
    type: str = "function"
    function: "FunctionRef"


@dataclass
class FunctionRef:
    """A function call requested by the model."""
    name: str
    arguments: str  # JSON string of the function arguments


# ─── Function calling ───────────────────────────────────────────────────────────

@dataclass
class FunctionDefinition:
    """A function definition for tool-use by the model."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for the function parameters


# ─── Response types ─────────────────────────────────────────────────────────────

@dataclass
class ChatCompletionChoice:
    """A single completion choice in the response."""
    message: Message
    finish_reason: str
    index: int


@dataclass
class UsageInfo:
    """Token usage information from the API."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class ChatCompletion:
    """A complete chat completion response."""
    id: str
    model: str
    choices: list[ChatCompletionChoice]
    usage: UsageInfo
    created: int


@dataclass
class StreamChunk:
    """A single chunk in a streaming response."""
    id: str
    delta: str
    index: int
    finish_reason: str | None


# ─── LLM Provider interface ────────────────────────────────────────────────────

class LLMProvider(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[Message],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        functions: list[FunctionDefinition] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatCompletion:
        """Send a chat completion request and return a typed response."""
        pass

    @abstractmethod
    async def stream_completion(
        self,
        messages: list[Message],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Coroutine[Any, Any, AsyncIterator[StreamChunk]]:
        """Yield streaming chunks for a chat completion."""
        ...


# ─── MiniMax provider ───────────────────────────────────────────────────────────

class MiniMaxProvider(LLMProvider):
    """
    MiniMax Chat Completions API implementation.

    API reference: https://www.minimaxi.com/document/Guides/Development/Audio API Complete
    Compatible with OpenAI Chat Completions API shape.
    """

    BASE_URL = "https://api.minimax.chat"
    CHAT_PATH = "/v1/text/chatcompletion_v2"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._settings = get_settings()
        self._api_key = api_key or self._settings.MINIMAX_API_KEY
        self._model = model or self._settings.MINIMAX_MODEL
        self._base_url = self._settings.MINIMAX_BASE_URL or self.BASE_URL

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _build_url(self) -> str:
        return f"{self._base_url}{self.CHAT_PATH}"

    async def chat_completion(
        self,
        messages: list[Message],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        functions: list[FunctionDefinition] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatCompletion:
        """
        Send a chat completion to MiniMax.
        Supports function calling via the functions parameter.
        """
        payload: dict[str, Any] = {
            "model": model or self._model,
            "messages": [self._message_to_dict(m) for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools
        if functions:
            payload["functions"] = [self._function_to_dict(f) for f in functions]

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self._build_url(),
                headers=self._build_headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return self._parse_response(data)

    async def stream_completion(
        self,
        messages: list[Message],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Yield streaming chunks from MiniMax SSE stream."""
        payload: dict[str, Any] = {
            "model": model or self._model,
            "messages": [self._message_to_dict(m) for m in messages],
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                self._build_url(),
                headers=self._build_headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    if line.strip() == "data: [DONE]":
                        break
                    chunk_data = line[len("data: "):]
                    yield self._parse_stream_chunk(chunk_data)

    def _message_to_dict(self, msg: Message) -> dict[str, Any]:
        result: dict[str, Any] = {
            "role": msg.role,
            "content": msg.content,
        }
        if msg.name:
            result["name"] = msg.name
        if msg.tool_call_id:
            result["tool_call_id"] = msg.tool_call_id
        return result

    def _function_to_dict(self, func: FunctionDefinition) -> dict[str, Any]:
        return {
            "name": func.name,
            "description": func.description,
            "parameters": func.parameters,
        }

    def _parse_response(self, data: dict[str, Any]) -> ChatCompletion:
        choices = []
        for choice_data in data.get("choices", []):
            msg_data = choice_data.get("message", {})
            message = Message(
                role=msg_data.get("role", "assistant"),
                content=msg_data.get("content", ""),
                name=msg_data.get("name"),
                tool_call_id=msg_data.get("tool_call_id"),
            )
            finish = choice_data.get("finish_reason", "")
            index = choice_data.get("index", 0)
            choices.append(ChatCompletionChoice(
                message=message,
                finish_reason=finish,
                index=index,
            ))

        usage_data = data.get("usage", {})
        usage = UsageInfo(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        return ChatCompletion(
            id=data.get("id", ""),
            model=data.get("model", self._model),
            choices=choices,
            usage=usage,
            created=data.get("created", 0),
        )

    def _parse_stream_chunk(self, line: str) -> StreamChunk:
        import json
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return StreamChunk(id="", delta="", index=0, finish_reason=None)

        delta = data.get("choices", [{}])[0].get("delta", "")
        finish = data.get("choices", [{}])[0].get("finish_reason")
        return StreamChunk(
            id=data.get("id", ""),
            delta=delta,
            index=data.get("choices", [{}])[0].get("index", 0),
            finish_reason=finish,
        )


# ─── Provider factory ───────────────────────────────────────────────────────────

_llm_providers: dict[str, type[LLMProvider]] = {
    "minimax": MiniMaxProvider,
    # OpenAI and Anthropic would be added here as additional providers
}


def create_llm_provider(
    provider: str | None = None,
    **kwargs,
) -> LLMProvider:
    """
    Factory function to create an LLM provider by name.
    Reads provider from settings if not specified.
    """
    settings = get_settings()
    provider_name = provider or settings.LLM_PROVIDER
    provider_class = _llm_providers.get(provider_name)
    if provider_class is None:
        raise ValueError(
            f"Unknown LLM provider {provider_name!r}. "
            f"Available: {list(_llm_providers.keys())}"
        )
    return provider_class(**kwargs)


async def chat_completion(
    messages: list[Message],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    functions: list[FunctionDefinition] | None = None,
) -> ChatCompletion:
    """Convenience function using the default provider from settings."""
    provider = create_llm_provider()
    return await provider.chat_completion(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        functions=functions,
    )
