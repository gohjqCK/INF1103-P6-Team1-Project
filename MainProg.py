import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# IO Manager Imports
from io_manager_modules.io_manager_cli import CLIIOManager
from io_manager_modules.io_manager_telegram import TelegramIOManager

# Safe Imports for Managers (Untouched)
try:
    from ai_manager_modules import ai_manager as AI_Manager_Module
    from ai_manager_modules.ai_manager_screening_task import AIScreener
    _AI_MANAGER_AVAILABLE = True
except Exception as err:
    AI_Manager_Module = None
    _AI_MANAGER_AVAILABLE = False

try:
    from data_manager_modules import Data_Manager as Data_Manager_Module
    from data_manager_modules.data_manager_resume_parser import DataManager as ResumeParser
    _DATA_MANAGER_AVAILABLE = True
except Exception as err:
    Data_Manager_Module = None
    _DATA_MANAGER_AVAILABLE = False

try:
    from Logic_manager_modules import Logic_Manager as Logic_Manager_Module
    from Logic_manager_modules.ResumeEvaluator import ResumeEvaluator
    _LOGIC_MANAGER_AVAILABLE = True
except Exception as err:
    Logic_Manager_Module = None
    _LOGIC_MANAGER_AVAILABLE = False

class MainProg:

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.resume_parser = ResumeParser() if _DATA_MANAGER_AVAILABLE and 'ResumeParser' in globals() else None
        self.ai_screener = AIScreener() if _AI_MANAGER_AVAILABLE and 'AIScreener' in globals() else None
        self.resume_evaluator = ResumeEvaluator() if _LOGIC_MANAGER_AVAILABLE and 'ResumeEvaluator' in globals() else None

    def check_ai_connection(self) -> bool:
        if _AI_MANAGER_AVAILABLE and hasattr(AI_Manager_Module, "check_connection"):
            try:
                return AI_Manager_Module.check_connection()
            except Exception:
                return False
        return False

    def run(self, employer_inputs: Dict[str, Any]) -> List[Dict[str, Any]]:
        rules = employer_inputs.get("business_rules", [])
        pdf_directory = employer_inputs.get("pdf_directory", "resumes")

        print(f"\n[Pipeline] Starting screening for: '{pdf_directory}' with {len(rules)} rule(s)...")

        # Stage 1: Keywords
        if self.check_ai_connection() and hasattr(AI_Manager_Module, "add_keywords"):
            try:
                rules = AI_Manager_Module.add_keywords(rules)
            except Exception:
                pass

        # Stage 2: Parse Resumes
        parsed_resumes = []
        if self.resume_parser and hasattr(self.resume_parser, "parse_from_url"):
            try:
                parsed_resumes = self.resume_parser.parse_from_url(pdf_directory)
            except Exception:
                pass
        if not parsed_resumes and _DATA_MANAGER_AVAILABLE and hasattr(Data_Manager_Module, "parse_resumes"):
            parsed_resumes = Data_Manager_Module.parse_resumes(folder=pdf_directory, output_file="resumes.json")

        if not parsed_resumes:
            print(f"  [!] No valid resumes found in '{pdf_directory}'.")
            return []

        # Stage 3: Screen Candidates
        screened_results = []
        if self.check_ai_connection():
            if self.ai_screener and hasattr(self.ai_screener, "screen"):
                screened_results = self.ai_screener.screen(rules, parsed_resumes)
            elif hasattr(AI_Manager_Module, "screen_resumes"):
                AI_Manager_Module.screen_resumes(rules, parsed_resumes, resumes_file="resumes.json", results_file="ai_output.json")
                if Path("ai_output.json").exists():
                    with open("ai_output.json", "r", encoding="utf-8") as f:
                        screened_results = json.load(f)

        if not screened_results and _LOGIC_MANAGER_AVAILABLE and hasattr(Logic_Manager_Module, "offline_screening_func"):
            try:
                screened_results = Logic_Manager_Module.offline_screening_func(parsed_resumes, rules)
            except Exception:
                screened_results = parsed_resumes

        # Stage 4: Filter and Sort
        sorted_candidates = []
        try:
            if self.resume_evaluator and hasattr(self.resume_evaluator, "filter_resumes") and hasattr(self.resume_evaluator, "sort_resumes"):
                accepted, rejected, invalid = self.resume_evaluator.filter_resumes(screened_results)
                if _DATA_MANAGER_AVAILABLE and hasattr(Data_Manager_Module, "outputfile_func"):
                    Data_Manager_Module.outputfile_func(accepted, rejected, invalid, str(self.output_dir))
                sorted_candidates = self.resume_evaluator.sort_resumes(accepted)
            elif _LOGIC_MANAGER_AVAILABLE and hasattr(Logic_Manager_Module, "filter_resume_func"):
                accepted, rejected, invalid = Logic_Manager_Module.filter_resume_func(screened_results)
                if _DATA_MANAGER_AVAILABLE and hasattr(Data_Manager_Module, "outputfile_func"):
                    Data_Manager_Module.outputfile_func(accepted, rejected, invalid, str(self.output_dir))
                sorted_candidates = Logic_Manager_Module.sort_resume_func(accepted) if hasattr(Logic_Manager_Module, "sort_resume_func") else accepted
            else:
                sorted_candidates = sorted(screened_results, key=lambda c: c.get("score", 0), reverse=True)
        except Exception:
            sorted_candidates = sorted(screened_results, key=lambda c: c.get("score", 0), reverse=True)

        print(f"[Pipeline Complete] Returned {len(sorted_candidates)} ranked candidate(s).\n")
        return sorted_candidates