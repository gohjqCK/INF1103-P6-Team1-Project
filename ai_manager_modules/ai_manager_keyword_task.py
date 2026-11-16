"""Asks the AI which keywords would prove a business rule."""
from langchain_core.prompts import ChatPromptTemplate

from ai_manager_modules.ai_manager_llm_error import LLMError
from ai_manager_modules.ai_manager_task import AITask
from ai_manager_modules.ai_manager_text_matcher import TextMatcher


class KeywordTask(AITask):
    """Turns one rule's text into a cleaned list of keywords."""
    # Key word prompt template. The AI is asked to return a JSON object with a list of keywords that would prove the rule.
    _PROMPT = ChatPromptTemplate.from_messages([
        ("system",
         "You help a hiring team check resumes against their rules. "
         "For the rule given, list 3 to 12 SHORT keywords (one or two words each) that a sentence from a resume "
         "would contain if it is about this rule. Include:\n"
         "- the main word and its other forms (singular, plural, -ing)\n"
         "- abbreviations and their full names\n"
         "- well-known products, tools or vendors that clearly prove the rule\n"
         "Do not include general words such as experience, years, skills, has, knowledge or certification.\n"
         'Example: for the rule "Knows relational databases" the keywords could be '
         '["database", "databases", "SQL", "MySQL", "PostgreSQL", "Oracle", "SQL Server"].\n'
         "If the rule is too general to check with specific words, give an empty list.\n"
         "Reply ONLY with JSON in exactly this format: "
         '{{"keywords": ["<keyword>", "..."]}}'),
        ("human", "Rule: {rule}"),
    ])

    
    def _build_prompt(self, task_input: str):
        """Builds the prompt using the rule set as input."""
        return self._PROMPT.invoke({"rule": task_input})

    """Parses the AI's reply and returns a list of keywords."""
    def _parse_reply(self, reply: dict, task_input: str) -> list[str]:
        suggested = reply.get("keywords")
        if not isinstance(suggested, list):
            raise LLMError("The AI's reply did not include a list of keywords.")
        keywords = self._remove_general_words(suggested)
        return self._add_word_forms(keywords)

    def _remove_general_words(self, suggested: list) -> list[str]:
        """Removes keywords that are too general to be useful"""
        keywords = []
        for word in suggested:
            word = str(word).strip()
            useful = []
            for part in word.lower().split():
                if not part.isdigit() and part not in TextMatcher.GENERAL_WORDS:
                    useful.append(part)
            if len(useful) > 0 and word not in keywords:
                keywords.append(word)
        return keywords

    def _add_word_forms(self, keywords: list[str]) -> list[str]:
        """Adds other forms of lower-case single words, e.g. "networking" -> "network", "networks"."""
        forms = []
        for word in keywords:
            if word.islower() and " " not in word and len(word) >= 4:
                if word.endswith("ing"):
                    forms.append(word[:-3])
                    forms.append(word[:-3] + "s")
                elif word.endswith("s"):
                    forms.append(word[:-1])
                else:
                    forms.append(word + "s")

        result = list(keywords)
        for form in forms:
            if form not in result:
                result.append(form)
        return result