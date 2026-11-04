"""The AI Manager's public interface, used by the rest of the application."""
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from ai_manager_modules.ai_manager_keyword_task import KeywordTask
from ai_manager_modules.ai_manager_llm_client import LLMClient
from ai_manager_modules.ai_manager_llm_error import LLMError
from ai_manager_modules.ai_manager_resume_scorer import ResumeScorer
from ai_manager_modules.ai_manager_screening_task import ScreeningTask


class AIManager:
    """Checks the connection, adds keywords to rules, and screens and scores resumes."""

    def __init__(self, client: LLMClient, max_workers: int = 4):
        self._client = client
        self._max_workers = max_workers
        self._keyword_task = KeywordTask(client)

    def check_connection(self) -> bool:
        """Returns True if the AI is ready to answer."""
        return self._client.is_available()

    def add_keywords(self, rules: list[dict]) -> list[dict]:
        """Adds a "keywords" list to every rule. A rule the AI fails on gets an empty list."""
        for rule in rules:
            try:
                rule["keywords"] = self._keyword_task.run(rule["text"])
            except LLMError:
                rule["keywords"] = []
        return rules

    def screen_resumes(self, rules: list[dict], resumes: list[dict],
                       on_result: Optional[Callable[[dict], None]] = None) -> list[dict]:
        """Screens every resume and returns the results: scored first, then rejected, then invalid."""
        task = ScreeningTask(self._client, rules)
        scorer = ResumeScorer(rules)

        def screen_and_report(resume: dict) -> dict:
            entry = self._screen_one(task, scorer, resume)
            if on_result is not None:
                on_result(entry)
            return entry

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            entries = list(executor.map(screen_and_report, resumes))

        ordered = []
        for outcome in ["scored", "rejected", "invalid"]:
            for entry in entries:
                if entry["outcome"] == outcome:
                    ordered.append(entry)
        return ordered

    def _screen_one(self, task: ScreeningTask, scorer: ResumeScorer, resume: dict) -> dict:
        """Screens one resume. Any failure marks only this resume invalid, so the batch carries on."""
        entry = self._empty_entry(resume)

        if resume.get("status") == "invalid":
            entry["outcome"] = "invalid"
            entry["reason"] = resume.get("reason", "")
            return entry

        try:
            result = task.run(resume)

            if result["document_type"] != "resume":
                entry["outcome"] = "invalid"
                entry["reason"] = f"Not a resume ({result['document_type']}): {result['doc_type_reason']}"
                return entry

            outcome = scorer.score(result["checks"], resume["text"])
        except Exception as error:
            entry["outcome"] = "invalid"
            entry["reason"] = f"Processing failed: {error}"
            return entry

        entry["reason"] = outcome["reason"]
        if outcome["rejected_by"]:
            entry["outcome"] = "rejected"
            return entry

        entry["outcome"] = "scored"
        entry["score"] = outcome["score"]
        entry.update(result["candidate_info"])
        return entry

    @staticmethod
    def _empty_entry(resume: dict) -> dict:
        """Returns a result with every field other managers expect."""
        return {
            "file": resume.get("file", ""),
            "name": "",
            "email": "",
            "phone": "",
            "outcome": "",
            "score": None,
            "reason": "",
            "summary": "",
            "skills": [],
            "qualifications": [],
            "work_experience": [],
            "projects": [],
        }