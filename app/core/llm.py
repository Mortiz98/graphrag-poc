"""LLM adapter — replaces langchain_openai.ChatOpenAI with Google GenAI."""

from __future__ import annotations

from collections.abc import Iterator

from app.core.genai import generate, generate_stream


class LLMResponse:
    def __init__(self, content: str):
        self.content = content


class LLM:
    def __init__(self, temperature: float = 0.0, streaming: bool = False):
        self.temperature = temperature
        self.streaming = streaming

    def invoke(self, messages: list[dict]) -> LLMResponse:
        system = ""
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system = content
            else:
                prompt_parts.append(content)
        prompt = "\n".join(prompt_parts) if len(prompt_parts) > 1 else (prompt_parts[0] if prompt_parts else "")
        text = generate(prompt=prompt, system=system, temperature=self.temperature)
        return LLMResponse(content=text)

    def stream(self, messages: list[dict]) -> Iterator[LLMResponse]:
        system = ""
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system = content
            else:
                prompt_parts.append(content)
        prompt = "\n".join(prompt_parts) if len(prompt_parts) > 1 else (prompt_parts[0] if prompt_parts else "")
        for token in generate_stream(prompt=prompt, system=system, temperature=self.temperature):
            yield LLMResponse(content=token)


def get_llm(temperature: float = 0.0, streaming: bool = False) -> LLM:
    from app.config import get_settings

    settings = get_settings()
    settings.validate_api_key()
    return LLM(temperature=temperature, streaming=streaming)
