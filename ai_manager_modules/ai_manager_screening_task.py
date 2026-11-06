"""Asks the AI to check one resume against the rules and extract the candidate's details."""
from datetime import date

from langchain_core.prompts import ChatPromptTemplate

from ai_manager_modules.ai_manager_llm_client import LLMClient
from ai_manager_modules.ai_manager_llm_error import LLMError
from ai_manager_modules.ai_manager_task import AITask
from ai_manager_modules.ai_manager_text_matcher import TextMatcher


class ScreeningTask(AITask):
    """Sends one resume to the AI, then validates and cleans every field of the reply before it is used."""

    _CONTACT_FIELDS = ["name", "email", "phone"]
    _LIST_FIELDS = ["qualifications", "work_experience", "projects"]

    _PROMPT = ChatPromptTemplate.from_messages([
        ("system",
         "You are an impartial resume screening assistant. Today is {today}.\n"
         "Analyze the given document and perform three tasks:\n"
         "1. Identify document_type: 'resume', 'job_description', 'guide_or_sample', or 'other'. "
         "If it is NOT a resume, set checks to [] and candidate_info to null.\n"
         "2. If it is a resume, check it ONLY against the provided numbered rules. "
         "Do not infer or guess. For evidence, quote exact text from the resume or use \"\".\n"
         "3. Extract key details into candidate_info (ignore personal attributes like age/gender/ethnicity).\n\n"
         "Reply strictly in this JSON format:\n"
         '{{\n'
         '  "document_type": "resume|job_description|guide_or_sample|other",\n'
         '  "doc_type_reason": "<one sentence explanation>",\n'
         '  "checks": [{{"id": 1, "evidence": "<exact quote or empty>", "shows": true|false}}],\n'
         '  "candidate_info": {{\n'
         '    "name": "...", "email": "...", "phone": "...", "summary": "<2-3 sentences>",\n'
         '    "skills": ["..."], "qualifications": ["..."], "work_experience": ["..."], "projects": ["..."]\n'
         '  }}\n'
         '}}'),
        ("human", "Rules:\n{rules}\n\nDocument:\n{resume}"),
    ])

    def __init__(self, client: LLMClient, rules: list[dict]):
        super().__init__(client)
        self._rules = rules

    def _build_prompt(self, task_input: dict):
        numbered_rules = []
        for number, rule in enumerate(self._rules, 1):
            numbered_rules.append(f"{number}. {rule['text']}")
        return self._PROMPT.invoke({
            "today": date.today().strftime("%d %B %Y"),
            "rules": "\n".join(numbered_rules),
            "resume": task_input["text"],
        })

    def _parse_reply(self, reply: dict, task_input: dict) -> dict:
        document_type = str(reply.get("document_type") or "unknown").lower()
        reason = str(reply.get("doc_type_reason") or "")

        if document_type != "resume":
            return {"document_type": document_type, "doc_type_reason": reason,
                    "checks": [], "candidate_info": {}}

        checks = reply.get("checks")
        if not isinstance(checks, list):
            raise LLMError("The AI's reply did not include the rule checks.")

        return {
            "document_type": document_type,
            "doc_type_reason": reason,
            "checks": self._clean_checks(checks),
            "candidate_info": self._clean_candidate_info(reply.get("candidate_info"), task_input["text"]),
        }

    def _clean_checks(self, checks: list) -> list[dict]:
        """Keeps only checks for a real rule, with the id, evidence and shows fields in a safe form."""
        cleaned = []
        for check in checks:
            if not isinstance(check, dict):
                continue
            rule_id = self._read_rule_id(check.get("id"))
            if rule_id is None:
                continue
            cleaned.append({
                "id": rule_id,
                "evidence": str(check.get("evidence") or ""),
                "shows": check.get("shows") is True,
            })
        return cleaned

    def _read_rule_id(self, value) -> int | None:
        """Returns the rule number, or None if it is missing, not a number, or not one of the rules."""
        try:
            rule_id = int(value)
        except (TypeError, ValueError):
            return None
        if 1 <= rule_id <= len(self._rules):
            return rule_id
        return None

    def _clean_candidate_info(self, info, resume_text: str) -> dict:
        """Fills in every field, keeping contact details and skills only if they are really in the resume."""
        if not isinstance(info, dict):
            info = {}
        matcher = TextMatcher(resume_text)
        cleaned = {"summary": str(info.get("summary") or "")}

        for field in self._CONTACT_FIELDS:
            value = str(info.get(field) or "")
            cleaned[field] = value if matcher.contains(value) else ""

        skills = self._read_list(info.get("skills"))
        cleaned["skills"] = [str(s) for s in skills if isinstance(s, str) and matcher.contains(s)]

        for field in self._LIST_FIELDS:
            items = self._read_list(info.get(field))
            cleaned[field] = [str(item) for item in items if isinstance(item, (str, int))]

        return cleaned

    @staticmethod
    def _read_list(value) -> list:
        """Returns the value if it is a list, otherwise an empty list."""
        return value if isinstance(value, list) else []