import unittest

from ai_manager_modules.ai_manager_keyword_task import KeywordTask
from ai_manager_modules.ai_manager_llm_error import LLMError
from ai_manager_modules.ai_manager_task import AITask
from tests.fake_llm_client import FakeLLMClient


class TestKeywordTask(unittest.TestCase):

    def _run_with_keywords(self, keywords):
        client = FakeLLMClient(reply={"keywords": keywords})
        return KeywordTask(client).run("any rule")

    def test_abstract_task_cannot_be_created_directly(self):
        with self.assertRaises(TypeError):
            AITask(FakeLLMClient())

    def test_rule_text_is_sent_to_the_ai(self):
        client = FakeLLMClient(reply={"keywords": []})
        KeywordTask(client).run("Knows Python")
        self.assertIn("Rule: Knows Python", client.prompts_received[0].to_string())

    def test_general_words_and_numbers_are_dropped(self):
        self.assertEqual(self._run_with_keywords(["experience", "2 years", "2"]), [])

    def test_two_word_keyword_is_kept_unchanged(self):
        self.assertEqual(self._run_with_keywords(["SQL Server"]), ["SQL Server"])

    def test_ing_word_gets_other_forms(self):
        result = self._run_with_keywords(["networking"])
        self.assertEqual(result, ["networking", "network", "networks"])

    def test_upper_case_and_short_words_get_no_forms(self):
        self.assertEqual(self._run_with_keywords(["CCNA", "aws"]), ["CCNA", "aws"])

    def test_duplicates_are_not_added(self):
        result = self._run_with_keywords(["firewall", "firewalls", "firewall"])
        self.assertEqual(result, ["firewall", "firewalls"])

    def test_empty_list_is_a_valid_reply(self):
        self.assertEqual(self._run_with_keywords([]), [])

    def test_missing_keywords_raises_llm_error(self):
        client = FakeLLMClient(reply={"other": "value"})
        with self.assertRaises(LLMError):
            KeywordTask(client).run("any rule")

    def test_keywords_not_a_list_raises_llm_error(self):
        client = FakeLLMClient(reply={"keywords": "python"})
        with self.assertRaises(LLMError):
            KeywordTask(client).run("any rule")

    def test_client_failure_reaches_the_caller(self):
        client = FakeLLMClient()
        with self.assertRaises(LLMError):
            KeywordTask(client).run("any rule")


if __name__ == "__main__":
    unittest.main()