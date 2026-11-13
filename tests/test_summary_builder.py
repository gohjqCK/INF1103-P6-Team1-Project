import unittest

from Logic_manager_modules.SummaryBuilder import SummaryBuilder

RULES = [
    {"text": "Python", "priority": "must"},
    {"text": "Cisco", "priority": "nice"},
    {"text": "criminal record", "priority": "reject"},
]


def make_entry(file, outcome, score=None, met=None, missed=None, rejected_by=None, reason=""):
    return {
        "file": file,
        "name": file.upper(),
        "outcome": outcome,
        "score": score,
        "reason": reason,
        "rules_met": met or [],
        "rules_missed": missed or [],
        "rejected_by": rejected_by or [],
    }


RESULTS = [
    make_entry("a.pdf", "scored", 100.0, met=["Python", "Cisco"]),
    make_entry("b.pdf", "scored", 66.7, met=["Python"], missed=["Cisco"]),
    make_entry("c.pdf", "scored", 0.0, missed=["Python", "Cisco"]),
    make_entry("d.pdf", "rejected", met=["Python"], missed=["Cisco"], rejected_by=["criminal record"]),
    make_entry("e.pdf", "invalid", reason="No readable text"),
]


class TestSummaryBuilder(unittest.TestCase):

    def _build(self, results=None, top_n=3):
        return SummaryBuilder(RULES, "test-model", top_n).build(RESULTS if results is None else results)

    def test_totals_count_each_outcome(self):
        self.assertEqual(self._build()["totals"], {"processed": 5, "scored": 3, "rejected": 1, "invalid": 1})

    def test_rule_statistics_count_scored_and_rejected_resumes(self):
        python = self._build()["rule_statistics"][0]
        self.assertEqual(python, {"rule": "Python", "priority": "must", "met": 3, "missed": 1, "percent_met": 75.0})

    def test_rule_statistics_count_knockout_rules(self):
        knockout = self._build()["rule_statistics"][2]
        self.assertEqual(knockout["met"], 1)
        self.assertEqual(knockout["missed"], 3)

    def test_score_statistics_use_only_scored_resumes(self):
        self.assertEqual(self._build()["score_statistics"],
                         {"average": 55.6, "median": 66.7, "highest": 100.0, "lowest": 0.0})

    def test_no_scored_resumes_gives_empty_score_statistics(self):
        statistics = self._build(results=[])["score_statistics"]
        self.assertIsNone(statistics["average"])
        self.assertIsNone(statistics["highest"])

    def test_no_resumes_gives_zero_percent(self):
        self.assertEqual(self._build(results=[])["rule_statistics"][0]["percent_met"], 0.0)

    def test_top_candidates_are_best_first_without_zero_scores(self):
        top = self._build()["top_candidates"]
        self.assertEqual([candidate["file"] for candidate in top], ["a.pdf", "b.pdf"])
        self.assertEqual(top[1]["rules_missed"], ["Cisco"])

    def test_top_candidates_respect_top_n(self):
        self.assertEqual(len(self._build(top_n=1)["top_candidates"]), 1)

    def test_equal_scores_are_ordered_by_file_name(self):
        results = [make_entry("z.pdf", "scored", 50.0), make_entry("m.pdf", "scored", 50.0)]
        top = self._build(results=results)["top_candidates"]
        self.assertEqual([candidate["file"] for candidate in top], ["m.pdf", "z.pdf"])

    def test_invalid_documents_list_file_and_reason(self):
        self.assertEqual(self._build()["invalid_documents"], [{"file": "e.pdf", "reason": "No readable text"}])

    def test_run_info_records_model_and_rules(self):
        run_info = self._build()["run_info"]
        self.assertEqual(run_info["model"], "test-model")
        self.assertEqual(run_info["rules"], ["Python", "Cisco", "criminal record"])
        self.assertTrue(run_info["generated_at"])

    def test_overall_summary_starts_empty(self):
        self.assertEqual(self._build()["overall_summary"], "")


if __name__ == "__main__":
    unittest.main()