import unittest

from ai_manager_modules.ai_manager_llm_error import LLMError
from ai_manager_modules.ai_manager_summary_task import SummaryTask
from tests.fake_llm_client import FakeLLMClient

REPORT = {
    "run_info": {"model": "not for the AI"},
    "totals": {"processed": 8, "scored": 5, "rejected": 2, "invalid": 1},
    "rule_statistics": [
        {"rule": "Python", "priority": "must", "met": 3, "missed": 4, "percent_met": 42.9},
        {"rule": "Cisco", "priority": "nice", "met": 1, "missed": 6, "percent_met": 14.3},
        {"rule": "criminal record", "priority": "reject", "met": 2, "missed": 5, "percent_met": 28.6},
    ],
    "score_statistics": {"average": 42.5},
    "top_candidates": [{"name": "Ada", "file": "ada.pdf", "score": 77.8}],
    "invalid_documents": [{"file": "not_for_the_ai.pdf"}],
}
COUNTS = ("Resumes received: 8. Checked against the rules: 7, of which 2 rejected by a knockout rule. "
          "Invalid and not checked: 1.")


class TestSummaryTask(unittest.TestCase):

    def _prompt_for(self, report):
        client = FakeLLMClient(reply={"overall_summary": "Good."})
        SummaryTask(client).run(report)
        return client.prompts_received[0].to_string()

    def _run_with_summary(self, summary):
        return SummaryTask(FakeLLMClient(reply={"overall_summary": summary})).run(REPORT)

    def test_rules_are_sent_from_least_met_to_most(self):
        prompt = self._prompt_for(REPORT)
        self.assertIn("'Cisco': met by 1 of 7 resumes (14.3%)", prompt)
        self.assertLess(prompt.index("'Cisco': met"), prompt.index("'Python': met"))

    def test_knockout_rules_are_not_sent(self):
        self.assertNotIn("criminal record", self._prompt_for(REPORT))

    def test_priority_labels_are_not_sent(self):
        self.assertNotIn("must", self._prompt_for(REPORT).split("Facts:")[1])

    def test_candidates_are_sent_with_their_scores(self):
        self.assertIn("Ada: score 77.8 out of 100", self._prompt_for(REPORT))

    def test_candidate_without_a_name_uses_the_file_name(self):
        report = {**REPORT, "top_candidates": [{"name": "", "file": "ada.pdf", "score": 77.8}]}
        self.assertIn("ada.pdf: score 77.8", self._prompt_for(report))

    def test_no_candidates_are_sent_as_none(self):
        report = {**REPORT, "top_candidates": []}
        self.assertIn("- None", self._prompt_for(report))

    def test_other_fields_are_not_sent(self):
        self.assertNotIn("not_for_the_ai.pdf", self._prompt_for(REPORT))

    def test_python_writes_the_counts_before_the_ai_text(self):
        result = self._run_with_summary("  Ada scored 77.8 out of 100.  ")
        self.assertEqual(result, f"{COUNTS} Ada scored 77.8 out of 100.")

    def test_missing_summary_raises_llm_error(self):
        with self.assertRaises(LLMError):
            SummaryTask(FakeLLMClient(reply={"other": "value"})).run(REPORT)

    def test_empty_summary_raises_llm_error(self):
        with self.assertRaises(LLMError):
            self._run_with_summary("   ")

    def test_summary_not_text_raises_llm_error(self):
        with self.assertRaises(LLMError):
            SummaryTask(FakeLLMClient(reply={"overall_summary": ["a", "b"]})).run(REPORT)

    def test_cut_off_summary_raises_llm_error(self):
        with self.assertRaises(LLMError):
            self._run_with_summary("The rule")

    def test_number_not_in_the_facts_raises_llm_error(self):
        with self.assertRaises(LLMError):
            self._run_with_summary("Ada scored 95.5 out of 100.")

    def test_client_failure_reaches_the_caller(self):
        with self.assertRaises(LLMError):
            SummaryTask(FakeLLMClient()).run(REPORT)


if __name__ == "__main__":
    unittest.main()