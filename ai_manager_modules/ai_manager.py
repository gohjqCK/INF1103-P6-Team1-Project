"""The AI Manager's public interface, used by the rest of the application."""
from concurrent.futures import ThreadPoolExecutor
import re
from typing import Callable, Optional

from ai_manager_modules.ai_manager_keyword_task import KeywordTask
from ai_manager_modules.ai_manager_llm_client import LLMClient
from ai_manager_modules.ai_manager_llm_error import LLMError
from ai_manager_modules.ai_manager_resume_scorer import ResumeScorer
from ai_manager_modules.ai_manager_screening_task import ScreeningTask
from ai_manager_modules.ai_manager_summary_task import SummaryTask


class AIManager:
    """Checks the connection, adds keywords to rules, screens and scores resumes, and writes the summary text."""

    _RULE_STOPWORDS = KeywordTask._GENERAL_WORDS | {
        "with", "such", "from", "into", "using", "than", "this", "that", "least",
        "must", "should", "able", "work", "working", "hands", "about",
    }
    
    def __init__(self, client: LLMClient, max_workers: int = 4):
        self._client = client
        self._max_workers = max_workers
        self._keyword_task = KeywordTask(client)
        self._summary_task = SummaryTask(client)

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
            entry = self._screen_one(task, scorer, resume, rules)
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

    @property
    def model_name(self) -> str:
        """The AI model's name, so Logic Manager can record it in the report."""
        return self._client.model_name

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
        entry["summary"] = self._reconcile_summary(
            entry.get("summary", ""),
            entry["rules_met"],
            entry["rules_missed"],
            rules or [],
        )
        return entry

    @classmethod
    def _reconcile_summary(
        cls,
        summary: str,
        rules_met: list[str],
        rules_missed: list[str],
        rules: list[dict],
    ) -> str:
        """Prevents candidate_info.summary from claiming skills or rules that the scorer marked missed."""
        if not summary or not rules_missed:
            return summary

        rule_by_text = {str(r.get("text", "")): r for r in (rules or [])}
        met_tokens = set()
        for r_text in rules_met:
            rule = rule_by_text.get(r_text, {})
            for kw in rule.get("keywords", []):
                met_tokens.update(re.findall(r"[a-z0-9]+", str(kw).lower()))
            for tok in re.findall(r"[a-z0-9]+", r_text.lower()):
                if len(tok) >= 3 and tok not in cls._RULE_STOPWORDS:
                    met_tokens.add(tok)

        cleaned = summary
        unmatched_notes = []
        for missed_text in rules_missed:
            rule = rule_by_text.get(missed_text, {})
            candidates = set()
            for kw in rule.get("keywords", []):
                for tok in re.findall(r"[a-z0-9]+", str(kw).lower()):
                    if len(tok) >= 3 and tok not in cls._RULE_STOPWORDS and tok not in met_tokens:
                        candidates.add(tok)
            for tok in re.findall(r"[a-z0-9]+", missed_text.lower()):
                if len(tok) >= 3 and tok not in cls._RULE_STOPWORDS and tok not in met_tokens:
                    candidates.add(tok)

            contradicted = False
            for tok in sorted(candidates, key=len, reverse=True):
                if re.search(rf"\b{re.escape(tok)}\b", cleaned, re.IGNORECASE):
                    contradicted = True
                    conj_pat = re.compile(
                        rf"(?:\s+and\s+|,\s*)(?:(?!\band\b)[^.,;\n])*?\b{re.escape(tok)}\b(?:\s+databases?)?",
                        re.IGNORECASE,
                    )
                    cleaned = conj_pat.sub(
                        lambda m: m.group(0)
                        if any(re.search(rf"\b{re.escape(mt)}\b", m.group(0).lower()) for mt in met_tokens)
                        else "",
                        cleaned,
                    )
            if contradicted and any(
                re.search(rf"\b{re.escape(tok)}\b", cleaned, re.IGNORECASE) for tok in candidates
            ):
                unmatched_notes.append(missed_text)

        cleaned = re.sub(r"\s{2,}", " ", cleaned).replace(" ,", ",").replace(" .", ".").strip()
        if unmatched_notes:
            note = "Note: Did not meet requirement(s): " + "; ".join(unmatched_notes) + "."
            if cleaned and not cleaned.endswith((".", "!", "?")):
                cleaned += "."
            cleaned = f"{cleaned} {note}".strip()
        return cleaned

    @staticmethod
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

    