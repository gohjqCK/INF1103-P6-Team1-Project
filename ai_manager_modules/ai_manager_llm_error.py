"""The one error type every AI client raises when it cannot get a usable reply."""


class LLMError(Exception):
    """The AI could not be reached, timed out, or replied with something unusable."""