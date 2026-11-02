"""Searches one piece of text, ignoring case and punctuation."""
import re
import unicodedata


class TextMatcher:
    """Holds one text in cleaned form and answers questions about it."""

    def __init__(self, text: str):
        self._cleaned_text = self._clean(text)

    @staticmethod
    def _clean(text: str) -> str:
        """Fixes PDF characters like the single letter 'fi', lowercases, and turns punctuation into spaces."""
        normalized = unicodedata.normalize("NFKC", text).lower()
        return re.sub(r"[^a-z0-9]+", " ", normalized)

    def contains(self, phrase: str) -> bool:
        """True if the phrase is anywhere in the text, even inside a longer word."""
        cleaned_phrase = self._clean(phrase).strip()
        if not cleaned_phrase:
            return False
        return cleaned_phrase in self._cleaned_text

    def has_any_word(self, words: list[str]) -> bool:
        """True if at least one of the words appears as a whole word."""
        for word in words:
            cleaned_word = self._clean(word).strip()
            if not cleaned_word:
                continue
            pattern = rf"\b{re.escape(cleaned_word)}\b"
            if re.search(pattern, self._cleaned_text):
                return True
        return False