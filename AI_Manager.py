# Temporary bridge: main.py still calls these three functions by name.
# Delete this file once main.py creates AIManager(OllamaClient()) and calls its methods.
import json

from ai_manager_modules.ai_manager import AIManager
from ai_manager_modules.ai_manager_ollama_client import OllamaClient


def check_connection() -> bool:
    return AIManager(OllamaClient()).check_connection()


def add_keywords(rules: list[dict]) -> list[dict]:
    return AIManager(OllamaClient()).add_keywords(rules)


def screen_resumes(rules: list[dict], resumes: list[dict], resumes_file: str = "resumes.json",
                   results_file: str = "ai_output.json", max_workers: int = 4) -> list[dict]:
    def show_progress(entry: dict) -> None:
        print(f"[{entry['file']}] -> Scored:{entry['score']}. Reason: {entry['reason']}")

    results = AIManager(OllamaClient(), max_workers).screen_resumes(rules, resumes, on_result=show_progress)
    with open(results_file, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=2, ensure_ascii=False)
    return results

def create_summary(rules: list[dict], results: list[dict], top_n: int = 3,
                    summary_file: str = "summary.json") -> dict:
        report = AIManager(OllamaClient()).create_summary(rules, results, top_n)
        with open(summary_file, "w", encoding="utf-8") as file:
            json.dump(report, file, indent=2, ensure_ascii=False)
        return report