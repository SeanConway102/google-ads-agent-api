"""
RED: Write the failing tests first.
Tests for src/llm/adapter.py — LLM provider interface and MiniMax implementation.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm.adapter import (
    Message,
    FunctionDefinition,
    ChatCompletion,
    UsageInfo,
    StreamChunk,
    MiniMaxProvider,
    create_llm_provider,
    chat_completion,
)


# ──────────────────────────────────────────────────────────────────────────────
# Shared mock settings
# ──────────────────────────────────────────────────────────────────────────────

def _mock_settings():
    m = MagicMock()
    m.MINIMAX_API_KEY = "test-key"
    m.MINIMAX_MODEL = "test-model"
    m.MINIMAX_BASE_URL = "https://api.minimax.chat"
    m.LLM_PROVIDER = "minimax"
    return m


# ──────────────────────────────────────────────────────────────────────────────
# Message dataclass tests
# ──────────────────────────────────────────────────────────────────────────────

class TestMessageDataclass:
    def test_message_system_role(self):
        msg = Message(role="system", content="You are helpful.")
        assert msg.role == "system"
        assert msg.content == "You are helpful."
        assert msg.name is None

    def test_message_with_name(self):
        msg = Message(role="user", content="Hello", name="user_1")
        assert msg.name == "user_1"

    def test_message_with_tool_call_id(self):
        msg = Message(role="tool", content="result", tool_call_id="call_123")
        assert msg.tool_call_id == "call_123"


# ──────────────────────────────────────────────────────────────────────────────
# FunctionDefinition tests
# ──────────────────────────────────────────────────────────────────────────────

class TestFunctionDefinition:
    def test_function_definition(self):
        func = FunctionDefinition(
            name="add_keywords",
            description="Add keywords to an ad group",
            parameters={
                "type": "object",
                "properties": {
                    "keywords": {"type": "array", "items": {"type": "string"}},
                },
            },
        )
        assert func.name == "add_keywords"
        assert func.parameters["type"] == "object"


# ──────────────────────────────────────────────────────────────────────────────
# ChatCompletion response parsing
# ──────────────────────────────────────────────────────────────────────────────

class TestChatCompletionParsing:
    def test_parse_full_response(self):
        with patch("src.llm.adapter.get_settings", _mock_settings):
            provider = MiniMaxProvider(api_key="test-key", model="test-model")
            data = {
                "id": "chatcmpl-123",
                "model": "test-model",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Green team proposes adding 'running shoes'.",
                        },
                        "finish_reason": "stop",
                        "index": 0,
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
                "created": 1234567890,
            }
            result = provider._parse_response(data)

            assert isinstance(result, ChatCompletion)
            assert result.id == "chatcmpl-123"
            assert result.model == "test-model"
            assert len(result.choices) == 1
            assert result.choices[0].message.content == "Green team proposes adding 'running shoes'."
            assert result.choices[0].finish_reason == "stop"
            assert result.usage.prompt_tokens == 100

    def test_parse_response_missing_id_raises_value_error(self):
        with patch("src.llm.adapter.get_settings", _mock_settings):
            provider = MiniMaxProvider(api_key="test-key")
            data = {"model": "test", "choices": []}
            with pytest.raises(ValueError, match="missing required field"):
                provider._parse_response(data)

    def test_parse_response_with_assistant_role(self):
        """Response with tool_calls on the message object."""
        with patch("src.llm.adapter.get_settings", _mock_settings):
            provider = MiniMaxProvider(api_key="test-key")
            data = {
                "id": "chatcmpl-456",
                "model": "test",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_abc",
                                    "function": {"name": "add_keywords", "arguments": '{"keywords": ["shoes"]}'},
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                        "index": 0,
                    }
                ],
                "created": 1234567890,
            }
            result = provider._parse_response(data)
            assert len(result.choices) == 1
            assert result.choices[0].message.content == ""
            # tool_calls are reflected in content/tool_call_id fields via _parse_response
            assert result.choices[0].finish_reason == "tool_calls"

    def test_parse_stream_chunk(self):
        with patch("src.llm.adapter.get_settings", _mock_settings):
            provider = MiniMaxProvider(api_key="test-key")
            line = '{"id":"chunk1","choices":[{"delta":"Hello","finish_reason":null,"index":0}]}'
            chunk = provider._parse_stream_chunk(line)

            assert isinstance(chunk, StreamChunk)
            assert chunk.id == "chunk1"
            assert chunk.delta == "Hello"
            assert chunk.index == 0
            assert chunk.finish_reason is None

    def test_parse_stream_chunk_invalid_json_raises(self):
        with patch("src.llm.adapter.get_settings", _mock_settings):
            provider = MiniMaxProvider(api_key="test-key")
            with pytest.raises(ValueError, match="Failed to parse stream chunk"):
                provider._parse_stream_chunk("not valid json")


# ──────────────────────────────────────────────────────────────────────────────
# MiniMaxProvider construction
# ──────────────────────────────────────────────────────────────────────────────

class TestMiniMaxProviderConstruction:
    def test_requires_api_key(self):
        with patch("src.llm.adapter.get_settings", _mock_settings):
            with pytest.raises(ValueError, match="MINIMAX_API_KEY is required"):
                MiniMaxProvider(api_key="")

    def test_uses_provided_api_key(self):
        with patch("src.llm.adapter.get_settings", _mock_settings):
            provider = MiniMaxProvider(api_key="my-key")
            assert provider._api_key == "my-key"

    def test_uses_provided_model(self):
        with patch("src.llm.adapter.get_settings", _mock_settings):
            provider = MiniMaxProvider(api_key="test", model="my-model")
            assert provider._model == "my-model"

    def test_build_url(self):
        with patch("src.llm.adapter.get_settings", _mock_settings):
            provider = MiniMaxProvider(api_key="test", model="test-model")
            assert provider._build_url() == "https://api.minimax.chat/v1/text/chatcompletion_v2"

    def test_build_headers(self):
        with patch("src.llm.adapter.get_settings", _mock_settings):
            provider = MiniMaxProvider(api_key="secret-key")
            headers = provider._build_headers()
            assert headers["Authorization"] == "Bearer secret-key"
            assert headers["Content-Type"] == "application/json"

    def test_message_to_dict(self):
        with patch("src.llm.adapter.get_settings", _mock_settings):
            provider = MiniMaxProvider(api_key="test")
            msg = Message(role="user", content="Hello", name="user_1")
            d = provider._message_to_dict(msg)
            assert d["role"] == "user"
            assert d["content"] == "Hello"
            assert d["name"] == "user_1"

    def test_message_to_dict_with_tool_call_id(self):
        with patch("src.llm.adapter.get_settings", _mock_settings):
            provider = MiniMaxProvider(api_key="test")
            msg = Message(role="tool", content="result", tool_call_id="call_xyz")
            d = provider._message_to_dict(msg)
            assert d["tool_call_id"] == "call_xyz"


# ──────────────────────────────────────────────────────────────────────────────
# create_llm_provider factory
# ──────────────────────────────────────────────────────────────────────────────

class TestCreateLLMProvider:
    def test_creates_minimax_provider_by_string(self):
        with patch("src.llm.adapter.get_settings", _mock_settings), \
             patch("src.config.get_settings", _mock_settings):
            provider = create_llm_provider("minimax")
            assert isinstance(provider, MiniMaxProvider)
            assert provider._api_key == "test-key"

    def test_raises_for_unknown_provider(self):
        with patch("src.llm.adapter.get_settings", _mock_settings), \
             patch("src.config.get_settings", _mock_settings):
            with pytest.raises(ValueError, match="Unknown LLM provider 'nonexistent'"):
                create_llm_provider("nonexistent")

    def test_unknown_provider_lists_available(self):
        with patch("src.llm.adapter.get_settings", _mock_settings), \
             patch("src.config.get_settings", _mock_settings):
            with pytest.raises(ValueError, match="Available:"):
                create_llm_provider("unknown_provider")


# ──────────────────────────────────────────────────────────────────────────────
# chat_completion convenience function
# ──────────────────────────────────────────────────────────────────────────────

class TestChatCompletionFunction:
    @pytest.mark.asyncio
    async def test_chat_completion_returns_chat_completion(self):
        with patch("src.llm.adapter.create_llm_provider") as mock_factory:
            mock_provider = MagicMock(spec=MiniMaxProvider)
            mock_response = ChatCompletion(
                id="test-id",
                model="test",
                choices=[],
                usage=UsageInfo(0, 0, 0),
                created=0,
            )
            mock_provider.chat_completion = AsyncMock(return_value=mock_response)
            mock_factory.return_value = mock_provider

            messages = [Message(role="user", content="Hello")]
            result = await chat_completion(messages)

            assert isinstance(result, ChatCompletion)
            assert result.id == "test-id"
            mock_factory.assert_called_once_with()
