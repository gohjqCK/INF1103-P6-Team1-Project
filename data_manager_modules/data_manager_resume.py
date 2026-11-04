"""Data model encapsulating individual resume state and validation logic."""
from typing import Dict, Any, Tuple


class Resume:
    """Represents an individual resume document and encapsulates validation rules."""
    
    MIN_TEXT_LENGTH = 200
    MAX_TEXT_LENGTH = 20000

    def __init__(self, file_name: str, raw_text: str = "", pages: int = 0, error_message: str = ""):
        self.file_name = file_name
        self.raw_text = raw_text.strip()
        self.pages = pages
        self.error_message = error_message
        self.status, self.reason = self._validate()

    def _validate(self) -> Tuple[str, str]:
        """Evaluates whether the extracted text is valid for downstream processing."""
        if self.error_message:
            return "invalid", self.error_message
        elif len(self.raw_text) < self.MIN_TEXT_LENGTH:
            return "invalid", "No readable text (it may be a scanned image)"
        elif len(self.raw_text) > self.MAX_TEXT_LENGTH:
            return "invalid", f"Too long for one resume ({self.pages} pages)"
        return "valid", ""

    def to_dict(self) -> Dict[str, Any]:
        """Converts object state to a dictionary for JSON serialization."""
        return {
            "file": self.file_name,
            "status": self.status,
            "reason": self.reason,
            "pages": self.pages,
            "text": self.raw_text
        }

    def to_db_record(self) -> Dict[str, Any]:
        """Formats the payload for the Supabase parsed_resumes table."""
        return {
            "file_name": self.file_name,
            "status": self.status,
            "reason": self.reason,
            "pages": self.pages,
            "full_text": self.raw_text
        }