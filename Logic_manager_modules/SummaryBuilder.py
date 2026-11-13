"""Calculates the facts in the summary report. Every number here comes from Python, not the AI."""
from datetime import datetime, timedelta, timezone
from statistics import mean, median


class SummaryBuilder:
    """Turns one batch of screening results into a report, leaving overall_summary for the AI to write."""

    _SINGAPORE_TIME = timezone(timedelta(hours=8))

    def __init__(self, rules: list[dict], model_name: str, top_n: int = 3):
        self._rules = rules
        self._model_name = model_name
        self._top_n = top_n

    def build(self, results: list[dict]) -> dict:
        scored = self._with_outcome(results, "scored")
        rejected = self._with_outcome(results, "rejected")
        invalid = self._with_outcome(results, "invalid")
        return {
            "run_info": self._run_info(),
            "totals": {
                "processed": len(results),
                "scored": len(scored),
                "rejected": len(rejected),
                "invalid": len(invalid),
            },
            "rule_statistics": self._rule_statistics(scored + rejected),
            "score_statistics": self._score_statistics(scored),
            "top_candidates": self._top_candidates(scored),
            "invalid_documents": self._invalid_documents(invalid),
            "overall_summary": "",
        }

    @staticmethod
    def _with_outcome(results: list[dict], outcome: str) -> list[dict]:
        return [entry for entry in results if entry["outcome"] == outcome]

    def _run_info(self) -> dict:
        return {
            "generated_at": datetime.now(self._SINGAPORE_TIME).strftime("%Y-%m-%d %H:%M:%S"),
            "model": self._model_name,
            "rules": [rule["text"] for rule in self._rules],
        }

    def _rule_statistics(self, checked: list[dict]) -> list[dict]:
        """Counts every resume checked against the rules. Invalid documents never were, so they are left out."""
        statistics = []
        for rule in self._rules:
            met = 0
            for entry in checked:
                if rule["text"] in entry["rules_met"] or rule["text"] in entry["rejected_by"]:
                    met += 1
            percent_met = round(met / len(checked) * 100, 1) if checked else 0.0
            statistics.append({
                "rule": rule["text"],
                "priority": rule["priority"],
                "met": met,
                "missed": len(checked) - met,
                "percent_met": percent_met,
            })
        return statistics

    @staticmethod
    def _score_statistics(scored: list[dict]) -> dict:
        if not scored:
            return {"average": None, "median": None, "highest": None, "lowest": None}
        scores = [entry["score"] for entry in scored]
        return {
            "average": round(mean(scores), 1),
            "median": round(median(scores), 1),
            "highest": max(scores),
            "lowest": min(scores),
        }

    def _top_candidates(self, scored: list[dict]) -> list[dict]:
        """Returns the best resumes. A score of 0 is left out, matching the Logic Manager's ranking."""
        above_zero = [entry for entry in scored if entry["score"] > 0]
        ranked = sorted(above_zero, key=lambda entry: (-entry["score"], entry["file"]))
        top = []
        for entry in ranked[:self._top_n]:
            top.append({
                "name": entry["name"],
                "file": entry["file"],
                "score": entry["score"],
                "rules_met": entry["rules_met"],
                "rules_missed": entry["rules_missed"],
            })
        return top

    @staticmethod
    def _invalid_documents(invalid: list[dict]) -> list[dict]:
        return [{"file": entry["file"], "reason": entry["reason"]} for entry in invalid]