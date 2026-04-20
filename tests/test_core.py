"""Unit tests for core modules (graph, vectorstore, genai)."""

from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.core.genai import reset_genai_client
from app.core.graph import check_nebula_health, get_nebula_session, reset_pool


class TestSettingsValidation:
    def test_empty_api_key_raises_error(self):
        settings = Settings(gemini_api_key="")
        with pytest.raises(ValueError, match="No API key configured"):
            settings.validate_api_key()

    def test_valid_api_key_passes(self):
        settings = Settings(gemini_api_key="test-key-123")
        settings.validate_api_key()

    def test_is_llm_configured_false_when_empty(self):
        settings = Settings(gemini_api_key="")
        assert settings.is_llm_configured is False

    def test_is_llm_configured_true_when_valid(self):
        settings = Settings(gemini_api_key="test-key-123")
        assert settings.is_llm_configured is True

    def test_is_gemini_configured_true_when_key_set(self):
        settings = Settings(gemini_api_key="test-key-123")
        assert settings.is_gemini_configured is True


class TestGetNebulaSession:
    @patch("app.core.graph._get_pool")
    def test_session_context_manager(self, mock_get_pool):
        mock_pool = MagicMock()
        mock_session = MagicMock()
        mock_pool.get_session.return_value = mock_session
        mock_get_pool.return_value = mock_pool

        with get_nebula_session() as session:
            assert session == mock_session

        mock_session.release.assert_called_once()

    @patch("app.core.graph._get_pool")
    def test_session_released_on_exception(self, mock_get_pool):
        mock_pool = MagicMock()
        mock_session = MagicMock()
        mock_pool.get_session.return_value = mock_session
        mock_get_pool.return_value = mock_pool

        try:
            with get_nebula_session():
                raise ValueError("test error")
        except ValueError:
            pass

        mock_session.release.assert_called_once()


class TestCheckNebulaHealth:
    @patch("app.core.graph.get_nebula_session")
    def test_healthy(self, mock_session_ctx):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.is_succeeded.return_value = True
        mock_session.execute.return_value = mock_result
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = check_nebula_health()
        assert result is True

    @patch("app.core.graph.get_nebula_session")
    def test_unhealthy(self, mock_session_ctx):
        mock_session_ctx.return_value.__enter__ = MagicMock(side_effect=ConnectionError("fail"))
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = check_nebula_health()
        assert result is False


class TestResetPool:
    @patch("app.core.graph._close_pool")
    def test_resets_pool(self, mock_close):
        import app.core.graph as graph_module

        graph_module._pool = MagicMock()
        reset_pool()
        mock_close.assert_called_once()


class TestResetGenaiClient:
    def test_resets_client(self):
        reset_genai_client()
        from app.core.genai import _client

        assert _client is None
