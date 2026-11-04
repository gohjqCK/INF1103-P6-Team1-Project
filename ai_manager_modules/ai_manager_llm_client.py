"""The contract every AI client must follow."""
from abc import ABC, abstractmethod
from typing import Any


class LLMClient(ABC):
    """Anything that can answer a prompt with JSON. Code that uses it never needs to know which AI is behind it."""

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the AI is ready to answer. Must not raise an error."""

    @abstractmethod
    def ask_for_json(self, prompt: Any) -> dict:
        """Returns the AI's reply as a dictionary. Raises LLMError if there is no usable reply."""