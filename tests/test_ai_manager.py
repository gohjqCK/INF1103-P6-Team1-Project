import unittest
from unittest.mock import Mock

from ai_manager_modules.ai_manager import AIManager
from ai_manager_modules.ai_manager_llm_client import LLMClient
from ai_manager_modules.ai_manager_llm_error import LLMError
from tests.fake_llm_client import FakeLLMClient

RULES = [
    {"text": "Python", "priority": "must", "keywords": ["python"]},
    {"text": "Cisco", "priority": "nice", "keywords": ["cisco"]},
    {"text": "criminal record", "priority": "reject", "keywords": ["criminal"]},
]


def make_resume(name, text):
    return {"file": name, "status": "valid", "reason": "", "pages": 1, "text": text}


class TestAIManager(unittest.TestCase):

    def _resume_reply(self, checks=None, candidate_info=None):
        return {"document_type": "resume", "checks": checks or [], "candidate_info": candidate_info}

    def test_connection_comes_from_the_client(self):
        self.assertTrue(AIManager(FakeLLMClient()).check_connection())
        self.assertFalse(AIManager(FakeLLMClient(available=False)).check_connection())

    def test_add_keywords_fills_in_every_rule(self):
        client = FakeLLMClient(reply={"keywords": ["SQL"]})
        rules = AIManager(client).add_keywords([{"text": "Knows SQL", "priority": "must"}])
        self.assertEqual(rules[0]["keywords"], ["SQL"])

    def test_add_keywords_failure_gives_empty_list(self):
        rules = AIManager(FakeLLMClient()).add_keywords([{"text": "Knows SQL", "priority": "must"}])
        self.assertEqual(rules[0]["keywords"], [])

    def test_scored_resume_has_score_and_details(self):
        info = {"name": "Ada", "skills": ["Python"], "qualifications": ["BSc"]}
        client = FakeLLMClient(reply=self._resume_reply(candidate_info=info))
        results = AIManager(client).screen_resumes(RULES, [make_resume("a.pdf", "Ada knows Python")])
        self.assertEqual(results[0]["outcome"], "scored")
        self.assertEqual(results[0]["score"], 66.7)
        self.assertEqual(results[0]["name"], "Ada")
        self.assertEqual(results[0]["qualifications"], ["BSc"])

    def test_verified_ai_answer_earns_the_rule(self):
        rules = [{"text": "Knows networking", "priority": "must", "keywords": ["network"]}]
        checks = [{"id": 1, "evidence": "Built a large network", "shows": True}]
        client = FakeLLMClient(reply=self._resume_reply(checks=checks))
        results = AIManager(client).screen_resumes(rules, [make_resume("a.pdf", "Built a large network")])
        self.assertEqual(results[0]["score"], 100.0)

    def test_made_up_quote_earns_nothing(self):
        rules = [{"text": "Knows networking", "priority": "must", "keywords": ["network"]}]
        checks = [{"id": 1, "evidence": "Built a large network", "shows": True}]
        client = FakeLLMClient(reply=self._resume_reply(checks=checks))
        results = AIManager(client).screen_resumes(rules, [make_resume("a.pdf", "Only wrote web pages")])
        self.assertEqual(results[0]["score"], 0.0)
        self.assertIn("Ignored 1 unverified", results[0]["reason"])

    def test_knockout_rule_rejects_the_resume(self):
        checks = [{"id": 3, "evidence": "has a criminal record", "shows": True}]
        client = FakeLLMClient(reply=self._resume_reply(checks=checks))
        results = AIManager(client).screen_resumes(RULES, [make_resume("a.pdf", "Ada has a criminal record")])
        self.assertEqual(results[0]["outcome"], "rejected")
        self.assertIsNone(results[0]["score"])

    def test_document_that_is_not_a_resume_is_invalid(self):
        client = FakeLLMClient(reply={"document_type": "other", "doc_type_reason": "A recipe."})
        results = AIManager(client).screen_resumes(RULES, [make_resume("a.pdf", "Add flour")])
        self.assertEqual(results[0]["outcome"], "invalid")
        self.assertIn("A recipe.", results[0]["reason"])

    def test_invalid_resume_skips_the_ai(self):
        client = FakeLLMClient(reply=self._resume_reply())
        resume = {"file": "scan.pdf", "status": "invalid", "reason": "No readable text", "text": ""}
        results = AIManager(client).screen_resumes(RULES, [resume])
        self.assertEqual(results[0]["reason"], "No readable text")
        self.assertEqual(client.prompts_received, [])

    def test_one_failure_does_not_stop_the_batch(self):
        def reply_or_fail(prompt):
            if "BROKEN" in prompt.to_string():
                raise LLMError("timed out")
            return self._resume_reply()

        client = Mock(spec=LLMClient)
        client.ask_for_json.side_effect = reply_or_fail
        resumes = [make_resume("bad.pdf", "BROKEN"), make_resume("good.pdf", "Knows Python")]
        results = AIManager(client).screen_resumes(RULES, resumes)

        self.assertEqual(results[0]["file"], "good.pdf")
        self.assertEqual(results[0]["outcome"], "scored")
        self.assertEqual(results[1]["file"], "bad.pdf")
        self.assertEqual(results[1]["outcome"], "invalid")
        self.assertIn("timed out", results[1]["reason"])

    def test_results_are_ordered_scored_rejected_invalid(self):
        def reply_for(prompt):
            text = prompt.to_string()
            if "REJECT" in text:
                return self._resume_reply(checks=[{"id": 3, "evidence": "criminal record REJECT", "shows": True}])
            if "RECIPE" in text:
                return {"document_type": "other"}
            return self._resume_reply()

        client = Mock(spec=LLMClient)
        client.ask_for_json.side_effect = reply_for
        resumes = [
            make_resume("invalid.pdf", "RECIPE"),
            make_resume("rejected.pdf", "criminal record REJECT"),
            make_resume("scored.pdf", "Knows Python"),
        ]
        results = AIManager(client).screen_resumes(RULES, resumes)
        self.assertEqual([r["file"] for r in results], ["scored.pdf", "rejected.pdf", "invalid.pdf"])

    def test_results_include_the_rules_met_and_missed(self):
        client = FakeLLMClient(reply=self._resume_reply())
        results = AIManager(client).screen_resumes(RULES, [make_resume("a.pdf", "Knows Python")])
        self.assertEqual(results[0]["rules_met"], ["Python"])
        self.assertEqual(results[0]["rules_missed"], ["Cisco"])
        self.assertEqual(results[0]["rejected_by"], [])

    def test_rejected_result_records_the_knockout_rule(self):
        checks = [{"id": 3, "evidence": "has a criminal record", "shows": True}]
        client = FakeLLMClient(reply=self._resume_reply(checks=checks))
        results = AIManager(client).screen_resumes(RULES, [make_resume("a.pdf", "Ada has a criminal record")])
        self.assertEqual(results[0]["rejected_by"], ["criminal record"])

    def test_create_summary_combines_numbers_and_ai_text(self):
        client = FakeLLMClient(reply=self._resume_reply())
        results = AIManager(client).screen_resumes(RULES, [make_resume("a.pdf", "Knows Python")])
        client = FakeLLMClient(reply={"overall_summary": "One applicant matched."})
        report = AIManager(client).create_summary(RULES, results)
        self.assertTrue(report["overall_summary"].endswith("One applicant matched."))
        self.assertEqual(report["totals"]["scored"], 1)
        self.assertEqual(report["run_info"]["model"], "fake-model")

    def test_create_summary_keeps_numbers_when_the_ai_fails(self):
        client = FakeLLMClient(reply=self._resume_reply())
        results = AIManager(client).screen_resumes(RULES, [make_resume("a.pdf", "Knows Python")])
        report = AIManager(FakeLLMClient()).create_summary(RULES, results)
        self.assertEqual(report["overall_summary"], "")
        self.assertEqual(report["rule_statistics"][0]["met"], 1)

    def test_create_summary_skips_the_ai_when_nothing_was_checked(self):
        client = FakeLLMClient(reply={"overall_summary": "Should not be used."})
        invalid = {"file": "x.pdf", "outcome": "invalid", "reason": "No text"}
        report = AIManager(client).create_summary(RULES, [invalid])
        self.assertEqual(report["overall_summary"], "")
        self.assertEqual(client.prompts_received, [])


    def test_on_result_is_called_for_every_resume(self):
        client = FakeLLMClient(reply=self._resume_reply())
        seen = []
        resumes = [make_resume("a.pdf", "x"), make_resume("b.pdf", "y")]
        AIManager(client).screen_resumes(RULES, resumes, on_result=lambda entry: seen.append(entry["file"]))
        self.assertEqual(sorted(seen), ["a.pdf", "b.pdf"])

    def test_results_keep_the_resume_id(self):
        client = FakeLLMClient(reply=self._resume_reply())
        scored = make_resume("a.pdf", "Ada knows Python")
        scored["id"] = 7
        invalid = {"id": 8, "file": "scan.pdf", "status": "invalid", "reason": "No readable text", "text": ""}

        results = AIManager(client).screen_resumes(RULES, [scored, invalid])

        ids = {entry["file"]: entry["id"] for entry in results}
        self.assertEqual(ids, {"a.pdf": 7, "scan.pdf": 8})


if __name__ == "__main__":
    unittest.main()