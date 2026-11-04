"""A pretend AI for tests, so they run without a live AI."""
from typing import Any

from ai_manager_modules.ai_manager_llm_client import LLMClient
from ai_manager_modules.ai_manager_llm_error import LLMError


class FakeLLMClient(LLMClient):
    """Gives back a prepared reply, or raises LLMError if no reply was prepared."""

    def __init__(self, reply: dict | None = None, available: bool = True):
        self._reply = reply
        self._available = available
        self.prompts_received = []

    def is_available(self) -> bool:
        return self._available

    def ask_for_json(self, prompt: Any) -> dict:
        self.prompts_received.append(prompt)
        if self._reply is None:
            raise LLMError("The fake AI has no reply prepared.")
        return self._reply