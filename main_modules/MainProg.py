import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
 
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_IMPORT_ERRORS: Dict[str, Exception] = {}

#AI Manager Imports
try:
    from ai_manager_modules.ai_manager import AIManager
    from ai_manager_modules.ai_manager_ollama_client import OllamaClient
except Exception as err:
    AIManager = None
    OllamaClient = None
    _IMPORT_ERRORS["AI Manager"] = err

##Data Manager Imports
try:
    from pypdf import PdfReader
    from data_manager_modules.data_manager_resume import Resume as ParsedResume
except Exception as err:
    PdfReader = None
    ParsedResume = None
    _IMPORT_ERRORS["Data Manager (PDF parsing)"] = err
try:
    from data_manager_modules.ResumeFolderParser import ResumeFolderParser
except Exception as err:
    ResumeFolderParser = None
    _IMPORT_ERRORS["Data Manager (PDF parsing)"] = err

##Logic Manager imports
try:
    from Logic_manager_modules import Logic_Manager as Logic_Manager_Module
    from Logic_manager_modules.Profile import Profile
    from Logic_manager_modules.ResumeEvaluator import ResumeEvaluator
except Exception as err:
    Logic_Manager_Module = None
    Profile = None
    ResumeEvaluator = None
    _IMPORT_ERRORS["Logic Manager"] = err
try:
    from Logic_manager_modules.OverviewReport import LogicReportGenerator
except Exception as err:
    LogicReportGenerator = None
    _IMPORT_ERRORS["Overview Report"] = err

class MainProg:

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
 
        for label, err in _IMPORT_ERRORS.items():
            print(f"  [!] {label} failed to import: {type(err).__name__}: {err}")

        self.ai_manager = None
        if AIManager is not None and OllamaClient is not None:
            try:
                self.ai_manager = AIManager(OllamaClient())
            except Exception as err:
                print(f"  [!] Could not create the AI Manager: {type(err).__name__}: {err}")
 
        self.report_generator = (LogicReportGenerator(str(self.output_dir)) if LogicReportGenerator else None)

        self.resume_parser = ResumeFolderParser() if ResumeFolderParser else None

    def check_ai_connection(self) -> bool:

        if self.ai_manager is None:
            return False
        try:
            return bool(self.ai_manager.check_connection())
        except Exception:
            return False

    def run(self, employer_inputs: Dict[str, Any]) -> List[Dict[str, Any]]:
        rules = [dict(rule) for rule in employer_inputs.get("business_rules", [])]
        pdf_directory = employer_inputs.get("pdf_directory", "resumes")
 
        print(f"\n[Pipeline] Starting screening for: '{pdf_directory}' with {len(rules)} rule(s)...")
 
        # Stage 1: Keywords (AI only)
        ai_online = self.check_ai_connection()
        if ai_online:
            print("  [AI] Ollama online - generating rule keywords.")
            rules = self.ai_manager.add_keywords(rules)
 
        # Stage 2: Parse Resumes
        parsed_resumes = self.resume_parser.parse(pdf_directory) if self.resume_parser else []
        if not parsed_resumes:
            print("[Pipeline] No resumes could be read.\n")
            return []
 
        # Stage 3: Screen Candidates (AI if Ollama is ready, otherwise offline fallback)
        if ai_online:
            print("  [AI] Using AI screening.")
            results = self.ai_manager.screen_resumes(rules, parsed_resumes)
        else:
            print(f"  [AI] Ollama unavailable - using offline screening.")
            valid = [r for r in parsed_resumes if r.get("status") == "valid"]
            invalid = [r for r in parsed_resumes if r.get("status") != "valid"]
            results = Logic_Manager_Module.offline_screening_func(valid, rules) if Logic_Manager_Module else valid
            for entry in invalid:
                entry["outcome"] = "invalid"
                entry["score"] = None
            results = results + invalid
 
        # Stage 4: Filter and Sort (save everything, then rank accepted candidates)
        self._save_results(results)
        ranked = [r for r in results if self._category(r) == "accepted"]
        ranked.sort(key=lambda c: c.get("score") or 0, reverse=True)
 
        print(f"[Pipeline Complete] Returned {len(ranked)} ranked candidate(s).\n")
        return ranked

    @staticmethod
    def _category(entry: Dict[str, Any]) -> str:
        """accepted / rejected (score 0) / invalid, decided by the Logic Manager's ResumeEvaluator."""
        if Profile is not None and ResumeEvaluator is not None:
            profile = Profile({
                "file": entry.get("file", ""),
                "outcome": entry.get("outcome", ""),
                "reason": entry.get("reason", ""),
                "score": entry.get("score"),
            })
            return ResumeEvaluator(profile).category()
        return "accepted" if entry.get("outcome") == "scored" and entry.get("score") else "invalid"
 
    def _save_results(self, results: List[Dict[str, Any]]) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        path = self.output_dir / f"screening_results_{stamp}.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        except Exception as err:
            print(f"  [!] Could not save results: {err}")
 
    def generate_overview_report(self, candidates: List[Dict[str, Any]]) -> Path:
        """Called by main.py after a run."""
        if self.report_generator is None:
            raise RuntimeError("Overview report generator is unavailable.")
        return self.report_generator.generate_overview_report(candidates)