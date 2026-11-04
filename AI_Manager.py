# AI Manager: checks, scores and summarises resumes with a local AI model (Ollama).
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from ai_manager_modules.ai_manager_keyword_task import KeywordTask
from ai_manager_modules.ai_manager_llm_client import LLMClient
from ai_manager_modules.ai_manager_llm_error import LLMError
from ai_manager_modules.ai_manager_ollama_client import OllamaClient
from ai_manager_modules.ai_manager_screening_task import ScreeningTask
from ai_manager_modules.ai_manager_text_matcher import TextMatcher

PRIORITY_WEIGHTS = {"must": 4, "important": 3, "nice": 2, "can consider": 1}


def evidence_is_valid(evidence: str, resume_text: str, keywords: list[str]) -> bool:
    if not evidence or not TextMatcher(resume_text).contains(evidence):
        return False
    if keywords and not TextMatcher(evidence).has_any_word(keywords):
        return False
    return True


def rule_text_in_resume(rule_text: str, resume_text: str) -> bool:
    words = rule_text.strip()
    return TextMatcher(resume_text).has_any_word([words, words + "s"])


def score_resume(rules: list[dict], checks: list[dict], resume_text: str) -> dict:
    shown, unproven = [], []
    for check in checks:
        rule_id = int(check.get("id", 0))
        evidence = str(check.get("evidence", ""))
        if check.get("shows"):
            kws = rules[rule_id - 1].get("keywords", []) if 1 <= rule_id <= len(rules) else []
            if evidence_is_valid(evidence, resume_text, kws):
                shown.append(rule_id)
            else:
                unproven.append(rule_id)

    # Exact-words check: the AI sometimes says "no" even when the skill is written in the resume.
    # Knockout ("reject") rules are skipped: "No criminal record" contains "criminal record".
    for idx, rule in enumerate(rules, 1):
        if rule["priority"] == "reject":
            continue
        if idx in shown:
            continue
        if rule_text_in_resume(rule["text"], resume_text):
            shown.append(idx)
            if idx in unproven:
                unproven.remove(idx)

    earned, total, musts_missed = 0, 0, 0
    met, missed, rejected_by = [], [], []

    for idx, rule in enumerate(rules, 1):
        priority = rule["priority"]
        if priority == "reject":
            if idx in shown:
                rejected_by.append(rule["text"])
        else:
            weight = PRIORITY_WEIGHTS.get(priority, 1)
            total += weight
            if idx in shown:
                earned += weight
                met.append(rule["text"])
            else:
                missed.append(rule["text"])
                if priority == "must":
                    musts_missed += 1

    score = round(earned / total * 100, 1) if total > 0 else 0.0

    if rejected_by:
        reason = "Rejected: " + "; ".join(rejected_by)
    elif not missed:
        reason = "Meets all rules."
    else:
        reason = f"Meets {len(met)}/{len(met)+len(missed)} rules. Missing: " + "; ".join(missed)

    if unproven:
        reason += f" (Ignored {len(unproven)} unverified claims)."

    return {"score": score, "rejected_by": rejected_by, "musts_missed": musts_missed, "reason": reason}


class AIManager:
    """The AI Manager's public interface: checks the connection, adds keywords and screens resumes."""

    def __init__(self, client: LLMClient, max_workers: int = 4):
        self._client = client
        self._max_workers = max_workers

    def check_connection(self) -> bool:
        """Returns True if the AI is ready to answer."""
        return self._client.is_available()

    def add_keywords(self, rules: list[dict]) -> list[dict]:
        """Adds a "keywords" list to every rule. A rule the AI fails on gets an empty list."""
        task = KeywordTask(self._client)
        for rule in rules:
            try:
                rule["keywords"] = task.run(rule["text"])
            except LLMError:
                rule["keywords"] = []
        return rules

    def screen_resumes(self, rules: list[dict], resumes: list[dict],
                       on_result: Optional[Callable[[dict], None]] = None) -> list[dict]:
        """Screens every resume and returns the results: scored first, then rejected, then invalid."""
        task = ScreeningTask(self._client, rules)

        def screen_and_report(resume: dict) -> dict:
            entry = self._screen_one(task, rules, resume)
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

    def _screen_one(self, task: ScreeningTask, rules: list[dict], resume: dict) -> dict:
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

            outcome = score_resume(rules, result["checks"], resume["text"])
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


# --- Temporary: main.py still calls these three functions by name. ---
# Delete them once main.py creates AIManager(OllamaClient()) and calls its methods.

def check_connection() -> bool:
    return AIManager(OllamaClient()).check_connection()


def add_keywords(rules: list[dict]) -> list[dict]:
    return AIManager(OllamaClient()).add_keywords(rules)


def screen_resumes(rules: list[dict], resumes: list[dict], resumes_file: str = "resumes.json",
                   results_file: str = "ai_output.json", max_workers: int = 4) -> list[dict]:
    def show_progress(entry: dict) -> None:
        print(f"[{entry['file']}] -> Scored:{entry['score']}. Reason: {entry['reason']}")

    results = AIManager(OllamaClient(), max_workers).screen_resumes(rules, resumes, on_result=show_progress)
    with open(results_file, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=2, ensure_ascii=False)
    return results