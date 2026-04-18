"""Unit tests for Gemini genai module."""

from unittest.mock import MagicMock, patch

from app.core.genai import generate, get_genai_client


class TestGetGenaiClient:
    @patch("app.core.genai.get_settings")
    def test_raises_when_api_key_missing(self, mock_settings):
        mock_settings.return_value.is_gemini_configured = False
        try:
            get_genai_client()
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "GEMINI_API_KEY" in str(e)

    @patch("app.core.genai.genai")
    @patch("app.core.genai.get_settings")
    def test_creates_client_with_api_key(self, mock_settings, mock_genai):
        mock_settings.return_value.is_gemini_configured = True
        mock_settings.return_value.gemini_api_key = "test-key"
        get_genai_client()
        mock_genai.Client.assert_called_once_with(api_key="test-key")


class TestGenerate:
    @patch("app.core.genai.get_genai_client")
    @patch("app.core.genai.get_settings")
    def test_generate_returns_text(self, mock_settings, mock_get_client):
        mock_settings.return_value.gemini_model = "gemini-2.0-flash"

        mock_response = MagicMock()
        mock_response.text = "  Hello from Gemini!  "
        mock_models = MagicMock()
        mock_models.generate_content.return_value = mock_response
        mock_client = MagicMock()
        mock_client.models = mock_models
        mock_get_client.return_value = mock_client

        result = generate("Say hello")
        assert result == "Hello from Gemini!"
        mock_models.generate_content.assert_called_once()

    @patch("app.core.genai.get_genai_client")
    @patch("app.core.genai.get_settings")
    def test_generate_empty_response(self, mock_settings, mock_get_client):
        mock_settings.return_value.gemini_model = "gemini-2.0-flash"

        mock_response = MagicMock()
        mock_response.text = None
        mock_models = MagicMock()
        mock_models.generate_content.return_value = mock_response
        mock_client = MagicMock()
        mock_client.models = mock_models
        mock_get_client.return_value = mock_client

        result = generate("Say hello")
        assert result == ""

    @patch("app.core.genai.get_genai_client")
    @patch("app.core.genai.get_settings")
    def test_generate_custom_model(self, mock_settings, mock_get_client):
        mock_settings.return_value.gemini_model = "gemini-2.0-flash"

        mock_response = MagicMock()
        mock_response.text = "Response"
        mock_models = MagicMock()
        mock_models.generate_content.return_value = mock_response
        mock_client = MagicMock()
        mock_client.models = mock_models
        mock_get_client.return_value = mock_client

        generate("Test", model="gemini-1.5-pro")
        call_kwargs = mock_models.generate_content.call_args
        assert call_kwargs.kwargs["model"] == "gemini-1.5-pro"
