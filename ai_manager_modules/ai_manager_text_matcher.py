"""Searches one piece of text, ignoring case and punctuation."""
import re
import unicodedata

# A tool that searches the raw resumes for evidence stated by the AI 
class TextMatcher:
    """Holds one text in cleaned form and answers questions about it."""
    
    GENERAL_WORDS = frozenset({
        "experience", "years", "year", "skills", "skill", "has", "have", "knowledge",
        "certification", "certifications", "certified", "record", "records", "related",
        "field", "good", "strong",
    })

    def __init__(self, text: str):
        self._cleaned_text = self._clean(text)

    @staticmethod
    # cleans the formatting of the file
    def _clean(text: str) -> str:
        """Fixes PDF characters like the single letter 'fi', lowercases, and turns punctuation into spaces."""
        normalized = unicodedata.normalize("NFKC", text).lower()
        return re.sub(r"[^a-z0-9]+", " ", normalized)

    # Format words
    def words(self) -> list[str]:
        """Returns the cleaned text as a list of words, in order."""
        return self._cleaned_text.split()

    # Checks if the phrase is found anywhere in the raw resume
    def contains(self, phrase: str) -> bool:
        """True if the phrase is anywhere in the text, even inside a longer word."""
        cleaned_phrase = self._clean(phrase).strip()
        if not cleaned_phrase:
            return False
        return cleaned_phrase in self._cleaned_text

    # Check for specific words
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