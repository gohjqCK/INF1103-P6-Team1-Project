import unittest

from ai_manager_modules.ai_manager_resume_scorer import ResumeScorer

NETWORKING = {"text": "Knows networking", "priority": "must", "keywords": ["network"]}
CLOUD = {"text": "Has cloud experience", "priority": "nice", "keywords": ["cloud", "AWS"]}
CRIME = {"text": "Has a criminal record", "priority": "reject", "keywords": ["criminal"]}


class TestResumeScorer(unittest.TestCase):

    def _yes(self, rule_id, evidence):
        return {"id": rule_id, "evidence": evidence, "shows": True}

    def test_score_uses_the_priority_weights(self):
        checks = [self._yes(1, "Built a large network")]
        result = ResumeScorer([NETWORKING, CLOUD]).score(checks, "Built a large network")
        self.assertEqual(result["score"], 66.7)
        self.assertEqual(result["reason"], "Meets 1/2 rules. Missing: Has cloud experience")
        
    def test_result_lists_rules_met_and_missed(self):
        checks = [self._yes(1, "Built a large network")]
        result = ResumeScorer([NETWORKING, CLOUD]).score(checks, "Built a large network")
        self.assertEqual(result["rules_met"], ["Knows networking"])
        self.assertEqual(result["rules_missed"], ["Has cloud experience"])

    def test_all_rules_met(self):
        checks = [self._yes(1, "Built a network on AWS"), self._yes(2, "Built a network on AWS")]
        result = ResumeScorer([NETWORKING, CLOUD]).score(checks, "Built a network on AWS")
        self.assertEqual(result["score"], 100.0)
        self.assertEqual(result["reason"], "Meets all rules.")

    def test_made_up_quote_earns_nothing(self):
        checks = [self._yes(1, "Built a large network")]
        result = ResumeScorer([NETWORKING]).score(checks, "Only wrote web pages")
        self.assertEqual(result["score"], 0.0)
        self.assertIn("Ignored 1 unverified", result["reason"])

    def test_real_quote_without_a_keyword_earns_nothing(self):
        checks = [self._yes(1, "wrote web pages")]
        result = ResumeScorer([NETWORKING]).score(checks, "Only wrote web pages")
        self.assertEqual(result["score"], 0.0)
        self.assertIn("Ignored 1 unverified", result["reason"])

    def test_empty_quote_earns_nothing(self):
        checks = [self._yes(1, "")]
        result = ResumeScorer([NETWORKING]).score(checks, "Only wrote web pages")
        self.assertEqual(result["score"], 0.0)

    def test_ai_saying_no_earns_nothing(self):
        checks = [{"id": 1, "evidence": "Built a network", "shows": False}]
        result = ResumeScorer([NETWORKING]).score(checks, "Built a network")
        self.assertEqual(result["score"], 0.0)
        self.assertNotIn("unverified", result["reason"])

    def test_rule_without_keywords_needs_only_a_real_quote(self):
        rule = {"text": "Works well in teams", "priority": "must", "keywords": []}
        result = ResumeScorer([rule]).score([self._yes(1, "led a team")], "I led a team")
        self.assertEqual(result["score"], 100.0)

    def test_exact_words_earn_the_rule_when_the_ai_missed_them(self):
        rule = {"text": "Python", "priority": "must", "keywords": ["python"]}
        result = ResumeScorer([rule]).score([], "Skills: Bash, Python")
        self.assertEqual(result["score"], 100.0)

    def test_exact_words_also_match_a_plural(self):
        rule = {"text": "firewall", "priority": "must", "keywords": []}
        result = ResumeScorer([rule]).score([], "Palo Alto firewalls")
        self.assertEqual(result["score"], 100.0)

    def test_exact_words_clear_an_unverified_claim(self):
        rule = {"text": "Python", "priority": "must", "keywords": ["python"]}
        checks = [self._yes(1, "made up quote about python")]
        result = ResumeScorer([rule]).score(checks, "Skills: Python")
        self.assertEqual(result["score"], 100.0)
        self.assertNotIn("unverified", result["reason"])

    def test_knockout_rule_rejects_with_real_evidence(self):
        checks = [self._yes(2, "has a criminal record")]
        result = ResumeScorer([NETWORKING, CRIME]).score(checks, "Ada has a criminal record")
        self.assertEqual(result["rejected_by"], ["Has a criminal record"])
        self.assertEqual(result["reason"], "Rejected: Has a criminal record")

    def test_knockout_rule_ignores_exact_words(self):
        rule = {"text": "criminal record", "priority": "reject", "keywords": ["criminal"]}
        result = ResumeScorer([rule]).score([], "No criminal record")
        self.assertEqual(result["rejected_by"], [])

    def test_knockout_rules_do_not_count_towards_the_total(self):
        checks = [self._yes(1, "Built a network")]
        result = ResumeScorer([NETWORKING, CRIME]).score(checks, "Built a network")
        self.assertEqual(result["score"], 100.0)

    def test_only_knockout_rules_scores_zero(self):
        result = ResumeScorer([CRIME]).score([], "Clean record")
        self.assertEqual(result["score"], 0.0)

    def test_unknown_priority_counts_as_one_point(self):
        rules = [{"text": "Python", "priority": "other", "keywords": []}, NETWORKING]
        result = ResumeScorer(rules).score([], "Skills: Python")
        self.assertEqual(result["score"], 20.0)

    def test_knockout_negated_evidence_does_not_reject(self):
        checks = [self._yes(1, "Clean criminal record and no prior offenses")]
        result = ResumeScorer([CRIME]).score(checks, "Clean criminal record and no prior offenses")
        self.assertEqual(result["rejected_by"], [])

    def test_core_keyword_rescues_multiword_rule_unless_missing_or_negated(self):
        sql_rule = {
            "text": "Hands-on experience with SQL databases",
            "priority": "must",
            "keywords": ["SQL", "database", "databases"],
        }
        checks = [{"id": 1, "evidence": "", "shows": False}]
        matched = ResumeScorer([sql_rule]).score(
            checks, "Backend project: optimize SQL/API response times"
        )
        self.assertEqual(matched["score"], 100.0)

        nosql_only = ResumeScorer([sql_rule]).score(checks, "Managed MongoDB databases")
        self.assertEqual(nosql_only["score"], 0.0)

        negated = ResumeScorer([sql_rule]).score(checks, "Candidate has no SQL background")
        self.assertEqual(negated["score"], 0.0)


if __name__ == "__main__":
    unittest.main()