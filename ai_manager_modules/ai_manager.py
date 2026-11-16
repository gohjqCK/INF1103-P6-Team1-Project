"""The AI Manager's public interface, used by the rest of the application."""
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from ai_manager_modules.ai_manager_keyword_task import KeywordTask
from ai_manager_modules.ai_manager_llm_client import LLMClient
from ai_manager_modules.ai_manager_llm_error import LLMError
from ai_manager_modules.ai_manager_resume_scorer import ResumeScorer
from ai_manager_modules.ai_manager_screening_task import ScreeningTask
from ai_manager_modules.ai_manager_summary_task import SummaryTask
from ai_manager_modules.ai_manager_summary_reconciler import SummaryReconciler


# Main AIManager class
class AIManager:
    """Checks the connection, adds keywords to rules, screens and scores resumes, and writes the summary text."""

    def __init__(self, client: LLMClient, max_workers: int = 4):
        self._client = client
        self._max_workers = max_workers
        self._keyword_task = KeywordTask(client)
        self._summary_task = SummaryTask(client)
        self._summary_reconciler = SummaryReconciler()

    # Checks if the AI is online
    def check_connection(self) -> bool:
        """Returns True if the AI is ready to answer."""
        return self._client.is_available()

    #Add keywords to every rule
    def add_keywords(self, rules: list[dict]) -> list[dict]:
        """Adds a "keywords" list to every rule. A rule the AI fails on gets an empty list."""
        for rule in rules:
            try:
                rule["keywords"] = self._keyword_task.run(rule["text"])
            except LLMError:
                rule["keywords"] = []
        return rules

    # Screen the entire batch of resumes
    def screen_resumes(self, rules: list[dict], resumes: list[dict], on_result: Optional[Callable[[dict], None]] = None) -> list[dict]:
        """Screens every resume and returns the results: scored first, then rejected, then invalid."""
        # One task and scorer shared by all resumes, since the rules are the same
        task = ScreeningTask(self._client, rules)
        scorer = ResumeScorer(rules)


        # executor.map passes one resume per call; this wrapper adds task, scorer, rules and progress reporting
        def screen_and_report(resume: dict) -> dict:
            entry = self._screen_one(task, scorer, resume, rules)
            if on_result is not None:
                on_result(entry)
            return entry

        # Screen several resumes at once; max_workers sets how many
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            entries = list(executor.map(screen_and_report, resumes))

        # Group the results by outcome
        ordered = []
        for outcome in ["scored", "rejected", "invalid"]:
            for entry in entries:
                if entry["outcome"] == outcome:
                    ordered.append(entry)
        return ordered

    @property
    def model_name(self) -> str:
        """The AI model's name, so Logic Manager can record it in the report."""
        # Gets the model
        return self._client.model_name
    

    # AI writes the summary
    def write_summary(self, report: dict) -> str:
        """Returns the AI-written summary of a report built by Logic Manager.
        Returns "" if no resumes were checked or the AI fails, so the report keeps its numbers.
        """
        checked = report["totals"]["scored"] + report["totals"]["rejected"]
        if checked == 0:
            return ""
        try:
            return self._summary_task.run(report)
        except LLMError:
            return ""


    # Runs the screening one resume at a time
    def _screen_one(
        self,
        task: ScreeningTask,
        scorer: ResumeScorer,
        resume: dict,
        rules: Optional[list[dict]] = None,
    ) -> dict:
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
        entry["rules_met"] = outcome["rules_met"]
        entry["rules_missed"] = outcome["rules_missed"]
        entry["rejected_by"] = outcome["rejected_by"]
        if outcome["rejected_by"]:
            entry["outcome"] = "rejected"
            return entry

        entry["outcome"] = "scored"
        entry["score"] = outcome["score"]
        entry.update(result["candidate_info"])
        entry["summary"] = self._summary_reconciler.reconcile(
            entry.get("summary", ""),
            entry["rules_met"],
            entry["rules_missed"],
            rules or [],
        )
        return entry

    @staticmethod
    # Blank result with every field other managers expect
    def _empty_entry(resume: dict) -> dict:
        """Returns a result with every field other managers expect."""
        return {
            "id": resume.get("id"),
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
            "rules_met": [],
            "rules_missed": [],
            "rejected_by": [],
        }

    