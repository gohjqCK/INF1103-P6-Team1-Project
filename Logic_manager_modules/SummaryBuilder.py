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

    @staticmethod
    def build_fallback_narrative(report: dict) -> str:
        """Deterministic narrative fallback used when the LLM summary fails, returns empty, or runs offline."""
        if not report or not isinstance(report, dict):
            return ""
        totals = report.get("totals") or {}
        processed = totals.get("processed", 0)
        scored = totals.get("scored", 0)
        rejected = totals.get("rejected", 0)
        invalid = totals.get("invalid", 0)
        checked = scored + rejected

        if checked == 0:
            return (
                f"Resumes received: {processed}. "
                f"Checked against the rules: 0. "
                f"Invalid and not checked: {invalid}."
            )

        counts = (
            f"Resumes received: {processed}. "
            f"Checked against the rules: {checked}, of which {rejected} rejected by a knockout rule. "
            f"Invalid and not checked: {invalid}."
        )

        normal_rules = [
            rule for rule in (report.get("rule_statistics") or [])
            if rule.get("priority") != "reject"
        ]
        rule_sentence = ""
        if normal_rules:
            lowest = min(normal_rules, key=lambda r: r.get("met", 0))
            rule_sentence = (
                f"The rule '{lowest.get('rule', '')}' was met by the fewest resumes "
                f"({lowest.get('met', 0)} of {checked}, {lowest.get('percent_met', 0.0)}%)."
            )

        top_candidates = report.get("top_candidates") or []
        if top_candidates:
            top = top_candidates[0]
            cand_name = top.get("name") or top.get("file") or "Unknown"
            cand_sentence = f"{cand_name} scored highest with {top.get('score')} out of 100."
        else:
            cand_sentence = "No candidate met any rule."

        return " ".join(part for part in (counts, rule_sentence, cand_sentence) if part)