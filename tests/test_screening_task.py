import unittest

from ai_manager_modules.ai_manager_llm_error import LLMError
from ai_manager_modules.ai_manager_screening_task import ScreeningTask
from tests.fake_llm_client import FakeLLMClient

RULES = [
    {"text": "Python", "priority": "must"},
    {"text": "Cisco", "priority": "nice"},
]
RESUME = {
    "file": "ada.pdf",
    "status": "valid",
    "reason": "",
    "pages": 1,
    "text": "Ada Lovelace ada@example.com Skills: Python and Cisco",
}


class TestScreeningTask(unittest.TestCase):

    def _run(self, reply):
        return ScreeningTask(FakeLLMClient(reply=reply), RULES).run(RESUME)

    def _run_resume_reply(self, checks=None, candidate_info=None):
        return self._run({"document_type": "resume", "checks": checks or [], "candidate_info": candidate_info})

    def test_rules_and_resume_are_sent_to_the_ai(self):
        client = FakeLLMClient(reply={"document_type": "other"})
        ScreeningTask(client, RULES).run(RESUME)
        prompt = client.prompts_received[0].to_string()
        self.assertIn("1. Python", prompt)
        self.assertIn("2. Cisco", prompt)
        self.assertIn(RESUME["text"], prompt)

    def test_not_a_resume_needs_no_checks(self):
        result = self._run({"document_type": "job_description", "doc_type_reason": "It lists duties."})
        self.assertEqual(result["document_type"], "job_description")
        self.assertEqual(result["doc_type_reason"], "It lists duties.")
        self.assertEqual(result["checks"], [])

    def test_missing_document_type_is_unknown(self):
        self.assertEqual(self._run({})["document_type"], "unknown")

    def test_missing_checks_raises_llm_error(self):
        with self.assertRaises(LLMError):
            self._run({"document_type": "resume"})

    def test_checks_not_a_list_raises_llm_error(self):
        with self.assertRaises(LLMError):
            self._run({"document_type": "resume", "checks": "yes"})

    def test_client_failure_reaches_the_caller(self):
        with self.assertRaises(LLMError):
            ScreeningTask(FakeLLMClient(), RULES).run(RESUME)

    def test_valid_check_is_kept(self):
        result = self._run_resume_reply(checks=[{"id": 1, "evidence": "Python", "shows": True}])
        self.assertEqual(result["checks"], [{"id": 1, "evidence": "Python", "shows": True}])

    def test_bad_rule_ids_are_skipped(self):
        checks = [
            {"id": None, "evidence": "Python", "shows": True},
            {"id": "abc", "evidence": "Python", "shows": True},
            {"id": 99, "evidence": "Python", "shows": True},
            "not a dictionary",
        ]
        self.assertEqual(self._run_resume_reply(checks=checks)["checks"], [])

    def test_null_evidence_becomes_empty_text(self):
        result = self._run_resume_reply(checks=[{"id": 1, "evidence": None, "shows": True}])
        self.assertEqual(result["checks"][0]["evidence"], "")

    def test_shows_must_really_be_true(self):
        result = self._run_resume_reply(checks=[{"id": 1, "evidence": "Python", "shows": "false"}])
        self.assertFalse(result["checks"][0]["shows"])

    def test_contact_details_must_be_in_the_resume(self):
        info = {"name": "Ada Lovelace", "email": "fake@example.com", "phone": None}
        result = self._run_resume_reply(candidate_info=info)["candidate_info"]
        self.assertEqual(result["name"], "Ada Lovelace")
        self.assertEqual(result["email"], "")
        self.assertEqual(result["phone"], "")

    def test_skills_must_be_in_the_resume(self):
        info = {"skills": ["Python", "Kubernetes", 5]}
        result = self._run_resume_reply(candidate_info=info)["candidate_info"]
        self.assertEqual(result["skills"], ["Python"])

    def test_other_lists_are_kept(self):
        info = {"qualifications": ["BSc"], "work_experience": ["Intern"], "projects": ["App"]}
        result = self._run_resume_reply(candidate_info=info)["candidate_info"]
        self.assertEqual(result["qualifications"], ["BSc"])
        self.assertEqual(result["work_experience"], ["Intern"])
        self.assertEqual(result["projects"], ["App"])

    def test_null_candidate_info_gives_empty_fields(self):
        result = self._run_resume_reply(candidate_info=None)["candidate_info"]
        self.assertEqual(result["name"], "")
        self.assertEqual(result["summary"], "")
        self.assertEqual(result["skills"], [])
        self.assertEqual(result["projects"], [])


if __name__ == "__main__":
    unittest.main()