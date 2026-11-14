import unittest

from Logic_manager_modules import Logic_Manager
from Logic_manager_modules.Offline_Screening import offline_screening_func
from Logic_manager_modules.OnlineResume import OnlineResume
from Logic_manager_modules.ResumeEvaluator import ResumeEvaluator


class TestLogicManagerAuditFixes(unittest.TestCase):
    def test_resume_evaluator_accepts_int_scores_and_rejects_bools(self):
        int_scored = OnlineResume({"file": "a.pdf", "outcome": "scored", "reason": "", "score": 80})
        bool_scored = OnlineResume({"file": "b.pdf", "outcome": "scored", "reason": "", "score": True})
        self.assertEqual(ResumeEvaluator.evaluate(int_scored), "accepted")
        self.assertEqual(ResumeEvaluator.evaluate(bool_scored), "invalid")

    def test_online_resume_defaults_missing_optional_fields(self):
        r = OnlineResume({"file": "ada.pdf", "outcome": "scored", "reason": "", "score": 90.0})
        self.assertEqual(r.get_name, "Unknown")
        self.assertEqual(r.get_summary, "No summary")
        self.assertEqual(r.get_projects, [])

    def test_validate_resume_helpers_report_accurate_positions(self):
        msg = Logic_Manager.validate_resume_func([{"outcome": "scored", "score": 10}, "not-a-dict"])
        self.assertIn("1 position", msg)

        key_msg = Logic_Manager.validate_resume_keys_func([{"file": "a.pdf"}])
        self.assertIn("outcome", key_msg)

    def test_offline_screening_populates_profile_fields(self):
        rules = [{"text": "Knows Python", "priority": "must", "keywords": ["python"]}]
        resumes = [{"file": "ada.pdf", "status": "valid", "text": "Ada Lovelace\nBuilt Python APIs"}]
        out = offline_screening_func(resumes, rules)
        self.assertEqual(out[0]["outcome"], "scored")
        self.assertIn("Knows Python", out[0]["skills"])
        self.assertTrue(out[0]["summary"])
        self.assertEqual(out[0]["projects"], [])


if __name__ == "__main__":
    unittest.main()
