"""Talks to a local AI model running in Ollama."""
import json
import os
from typing import Any

import ollama
from langchain_ollama import ChatOllama

from ai_manager_modules.ai_manager_llm_client import LLMClient
from ai_manager_modules.ai_manager_llm_error import LLMError


class OllamaClient(LLMClient):
    """Sends prompts to Ollama and turns every kind of failure into an LLMError."""

    DEFAULT_HOST = "http://localhost:11434"
    DEFAULT_MODEL = "qwen2.5:7b"
    CONNECTION_CHECK_SECONDS = 5

    def __init__(self, timeout_seconds: float = 600):
        self._host = os.getenv("OLLAMA_HOST", self.DEFAULT_HOST)
        self._model = os.getenv("OLLAMA_MODEL", self.DEFAULT_MODEL)
        self._llm = ChatOllama(
            model=self._model,
            base_url=self._host,
            temperature=0,
            format="json",
            seed=42,
            num_ctx=8192,
            client_kwargs={"timeout": timeout_seconds},
        )

    def is_available(self) -> bool:
        try:
            client = ollama.Client(host=self._host, timeout=self.CONNECTION_CHECK_SECONDS)
            downloaded = [model.model for model in client.list().models]
        except Exception:
            return False
        return self._model in downloaded or self._model + ":latest" in downloaded

    def ask_for_json(self, prompt: Any) -> dict:
        try:
            reply = self._llm.invoke(prompt)
        except Exception as error:
            raise LLMError(f"Could not get a reply from Ollama: {error}") from error

        try:
            data = json.loads(reply.content)
        except (TypeError, ValueError) as error:
            raise LLMError(f"The AI's reply was not valid JSON: {error}") from error

        if not isinstance(data, dict):
            raise LLMError("The AI's reply was JSON, but not a JSON object.")
        return data