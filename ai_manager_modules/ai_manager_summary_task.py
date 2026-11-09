"""Asks the AI to describe a batch of screening results in plain English."""
import re

from langchain_core.prompts import ChatPromptTemplate

from ai_manager_modules.ai_manager_llm_error import LLMError
from ai_manager_modules.ai_manager_task import AITask


class SummaryTask(AITask):
    """Writes a short summary: Python states the counts, and the AI describes the rules and candidates."""

    _KNOCKOUT = "reject"
    _NUMBER = re.compile(r"\d+(?:\.\d+)?")

    _PROMPT = ChatPromptTemplate.from_messages([
        ("system",
         "You write short reports for a hiring team, using ONLY the facts you are given.\n"
         "Write 1 or 2 plain sentences that say:\n"
         "1. Which rule the fewest resumes met, with the rule's wording and its percentage.\n"
         "2. Which candidate scored highest, with their score. If the candidates list says None, "
         "write exactly: No candidate met any rule.\n"
         "Copy every number and name exactly. Do not mention anything that is not in the facts, "
         "and do not give advice. Use single quotes, never double quotes, inside the summary.\n"
         "Reply ONLY with JSON in exactly this format: "
         '{{"overall_summary": "<1 or 2 sentences>"}}'),
        ("human", "Facts:\n{facts}"),
    ])

    def _build_prompt(self, task_input: dict):
        return self._PROMPT.invoke({"facts": self._write_facts(task_input)})

    def _parse_reply(self, reply: dict, task_input: dict) -> str:
        summary = reply.get("overall_summary")
        if not isinstance(summary, str) or not summary.strip():
            raise LLMError("The AI's reply did not include a written summary.")
        summary = summary.strip()
        if not summary.endswith((".", "!", "?")):
            raise LLMError("The AI's summary was cut off before the end of a sentence.")
        self._check_numbers(summary, task_input)
        return f"{self._write_counts(task_input)} {summary}"

    def _check_numbers(self, summary: str, report: dict) -> None:
        """Rejects a summary containing a number the AI was not given, apart from the 100 in a score out of 100."""
        allowed = set(self._NUMBER.findall(self._write_facts(report)))
        for number in self._NUMBER.findall(summary):
            if number not in allowed:
                raise LLMError(f"The AI's summary used a number that is not in the facts: {number}")

    @staticmethod
    def _write_counts(report: dict) -> str:
        """Written by Python, because the AI miscopied these counts when asked to repeat them."""
        totals = report["totals"]
        checked = totals["scored"] + totals["rejected"]
        return (f"Resumes received: {totals['processed']}. "
                f"Checked against the rules: {checked}, of which {totals['rejected']} rejected by a knockout rule. "
                f"Invalid and not checked: {totals['invalid']}.")

    def _write_facts(self, report: dict) -> str:
        """Writes the rules and candidates as plain sentences, because the AI misread the numbers in raw JSON."""
        checked = report["totals"]["scored"] + report["totals"]["rejected"]
        lines = ["Rules, from fewest resumes meeting them to most:"]

        normal_rules = [rule for rule in report["rule_statistics"] if rule["priority"] != self._KNOCKOUT]
        for rule in sorted(normal_rules, key=lambda rule: rule["met"]):
            lines.append(f"- '{rule['rule']}': met by {rule['met']} of {checked} resumes ({rule['percent_met']}%)")

        lines.append("Candidates, from highest score to lowest:")
        for candidate in report["top_candidates"]:
            lines.append(f"- {candidate['name'] or candidate['file']}: score {candidate['score']} out of 100")
        if not report["top_candidates"]:
            lines.append("- None")
        return "\n".join(lines)