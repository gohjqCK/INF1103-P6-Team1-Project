"""Abstract base class establishing the contract for all I/O managers."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseIOManager(ABC):
    """Formal interface contract for User Interfaces (CLI, Telegram, GUI).

    """

    @abstractmethod
    def display_message(self, message: str) -> None:
        """Displays standard informational messages."""
        pass

    @abstractmethod
    def display_error(self, error_message: str) -> None:
        """Displays highlighted error notifications."""
        pass

    @abstractmethod
    def display_success(self, success_message: str) -> None:
        """Displays highlighted confirmation notifications."""
        pass

    @abstractmethod
    def display_screening_results(
        self, ranked_candidates: List[Any], top_n: Optional[int] = None
    ) -> List[Any]:
        """Renders ranked candidate evaluations."""
        pass

    @abstractmethod
    def get_employer_inputs(self, rerun_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Collects and returns validated setup configurations from the user."""
        pass