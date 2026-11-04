import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ai_manager_modules.ai_manager_llm_client import LLMClient
from ai_manager_modules.ai_manager_llm_error import LLMError
from ai_manager_modules.ai_manager_ollama_client import OllamaClient
from tests.fake_llm_client import FakeLLMClient

OLLAMA_LIBRARY = "ai_manager_modules.ai_manager_ollama_client.ollama.Client"


class TestLLMClients(unittest.TestCase):

    def _client_replying(self, content):
        client = OllamaClient()
        client._llm = SimpleNamespace(invoke=lambda prompt: SimpleNamespace(content=content))
        return client

    def test_ollama_client_reports_its_model(self):
        self.assertEqual(OllamaClient().model_name, OllamaClient.DEFAULT_MODEL)
 

    def test_interface_cannot_be_created_directly(self):
        with self.assertRaises(TypeError):
            LLMClient()

    def test_valid_json_becomes_a_dictionary(self):
        client = self._client_replying('{"keywords": ["python"]}')
        self.assertEqual(client.ask_for_json("prompt"), {"keywords": ["python"]})

    def test_malformed_json_raises_llm_error(self):
        client = self._client_replying("this is not JSON")
        with self.assertRaises(LLMError):
            client.ask_for_json("prompt")

    def test_json_list_raises_llm_error(self):
        client = self._client_replying('["python"]')
        with self.assertRaises(LLMError):
            client.ask_for_json("prompt")

    def test_connection_failure_raises_llm_error(self):
        def fail(prompt):
            raise ConnectionError("Ollama is down")

        client = OllamaClient()
        client._llm = SimpleNamespace(invoke=fail)
        with self.assertRaises(LLMError):
            client.ask_for_json("prompt")

    def test_available_when_model_is_downloaded(self):
        models = [SimpleNamespace(model=OllamaClient.DEFAULT_MODEL)]
        with patch(OLLAMA_LIBRARY) as fake_library:
            fake_library.return_value.list.return_value = SimpleNamespace(models=models)
            self.assertTrue(OllamaClient().is_available())

    def test_not_available_when_model_is_missing(self):
        with patch(OLLAMA_LIBRARY) as fake_library:
            fake_library.return_value.list.return_value = SimpleNamespace(models=[])
            self.assertFalse(OllamaClient().is_available())

    def test_not_available_when_ollama_is_down(self):
        with patch(OLLAMA_LIBRARY, side_effect=ConnectionError("down")):
            self.assertFalse(OllamaClient().is_available())

    def test_fake_client_can_replace_the_real_one(self):
        client: LLMClient = FakeLLMClient(reply={"ok": True})
        self.assertTrue(client.is_available())
        self.assertEqual(client.ask_for_json("prompt"), {"ok": True})

    def test_fake_client_without_reply_raises_llm_error(self):
        with self.assertRaises(LLMError):
            FakeLLMClient().ask_for_json("prompt")


if __name__ == "__main__":
    unittest.main()