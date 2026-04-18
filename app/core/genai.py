"""Google Gemini integration for query expansion."""

from google import genai
from google.genai import types

from app.config import get_settings
from app.core import logger


def get_genai_client() -> genai.Client:
    """Create a Gemini client using the configured API key."""
    settings = get_settings()
    if not settings.is_gemini_configured:
        raise ValueError(
            "GEMINI_API_KEY not configured. "
            "Add your API key to the .env file. "
            "Get one at https://aistudio.google.com/apikey"
        )
    return genai.Client(api_key=settings.gemini_api_key)


def generate(prompt: str, model: str | None = None) -> str:
    """Generate a text response using Gemini.

    Args:
        prompt: The text prompt to send to Gemini.
        model: Override the model name. Defaults to config setting.

    Returns:
        The generated text content.
    """
    settings = get_settings()
    client = get_genai_client()
    model_name = model or settings.gemini_model

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=256,
        ),
    )

    text = response.text.strip() if response.text else ""
    logger.info("gemini_generate_completed", model=model_name, output_len=len(text))
    return text
