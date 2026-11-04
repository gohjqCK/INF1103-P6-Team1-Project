"""The steps every job given to the AI follows."""
from abc import ABC, abstractmethod
from typing import Any

from ai_manager_modules.ai_manager_llm_client import LLMClient


class AITask(ABC):
    """One job for the AI: build a prompt, ask the AI, then check and use its reply."""

    def __init__(self, client: LLMClient):
        self._client = client

    def run(self, task_input: Any) -> Any:
        """Runs the job. Raises LLMError if the AI fails or its reply is not usable."""
        prompt = self._build_prompt(task_input)
        reply = self._client.ask_for_json(prompt)
        return self._parse_reply(reply, task_input)

    @abstractmethod
    def _build_prompt(self, task_input: Any) -> Any:
        """Returns the prompt to send to the AI."""

    @abstractmethod
    def _parse_reply(self, reply: dict, task_input: Any) -> Any:
        """Checks the AI's reply and returns the result. Raises LLMError if the reply is not usable."""