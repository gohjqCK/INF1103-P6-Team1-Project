"""
main.py - INF1103 Phase 2 Central Coordinator
Runs CLI in the main thread and Telegram Bot in a background thread concurrently.
Integrates OOP Logic Manager modules, Data Manager, AI Manager, and dual I/O managers.
"""

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

# Load environment variables (.env)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import I/O Manager Modules
from io_manager_modules.io_manager_cli import CLIIOManager
from io_manager_modules.io_manager_telegram import TelegramIOManager

# Safe imports for team managers
try:
    import AI_Manager
    _AI_MANAGER_AVAILABLE = True
except Exception as err:
    AI_Manager = None
    _AI_MANAGER_AVAILABLE = False
    print(f"  [Notice] AI_Manager could not be loaded ({err}). Will use offline screening.")

try:
    import Data_Manager
    _DATA_MANAGER_AVAILABLE = True
except Exception as err:
    Data_Manager = None
    _DATA_MANAGER_AVAILABLE = False
    print(f"  [Notice] Data_Manager could not be loaded ({err}).")

# Import new OOP Logic Manager Modules
try:
    import Logic_manager_modules.Logic_Manager as Logic_Manager
    from Logic_manager_modules.ResultsPath import ResultsPath
    from Logic_manager_modules.ResultsData import ResultsData
    _LOGIC_MODULES_AVAILABLE = True
except Exception as err:
    Logic_Manager = None
    _LOGIC_MODULES_AVAILABLE = False
    print(f"  [Notice] Logic_manager_modules could not be loaded ({err}).")

AI_OUTPUT_FILE = "ai_output.json"


# =============================================================================
# Pipeline Coordinator (Shared by both CLI and Telegram Bot)
# =============================================================================

def execute_screening_pipeline(employer_inputs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Executes the 4-stage screening pipeline.
    Bridges Data_Manager, AI_Manager, and Jerald's new Logic_manager_modules.
    """
    rules = employer_inputs.get("business_rules", [])
    pdf_directory = employer_inputs.get("pdf_directory", "resumes")
    top_n = employer_inputs.get("top_n", 3)
    out_dir = Path(employer_inputs.get("output_directory", "output"))
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[Pipeline] Starting screening run for directory: '{pdf_directory}' with {len(rules)} rule(s)...")

    # -------------------------------------------------------------------------
    # Stage 1: Generate AI Prompt / Keywords from Rules
    # -------------------------------------------------------------------------
    if _AI_MANAGER_AVAILABLE and hasattr(AI_Manager, "check_connection"):
        try:
            if AI_Manager.check_connection():
                print("  [Stage 1/4] Generating AI prompt keywords via Ollama...")
                rules = AI_Manager.add_keywords(rules)
            else:
                print("  [Stage 1/4] Ollama server offline. Skipping keyword generation.")
        except Exception as err:
            print(f"  [Stage 1/4] Notice: keyword generation skipped ({err}).")
    else:
        print("  [Stage 1/4] AI Manager offline. Skipping keyword generation.")

    # -------------------------------------------------------------------------
    # Stage 2: Parse PDF Resumes (Data Manager)
    # -------------------------------------------------------------------------
    print(f"  [Stage 2/4] Parsing resumes from '{pdf_directory}'...")
    resumes_json_path = "resumes.json"
    parsed_resumes: List[Dict[str, Any]] = []

    if _DATA_MANAGER_AVAILABLE and hasattr(Data_Manager, "parse_resumes"):
        parsed_resumes = Data_Manager.parse_resumes(folder=pdf_directory, output_file=resumes_json_path)
    else:
        print("  [!] Data_Manager not available to parse resumes.")

    if not parsed_resumes:
        print(f"  [!] No valid resumes found in '{pdf_directory}'.")
        return []

    # -------------------------------------------------------------------------
    # Stage 3 & 4: Screen, Filter, and Sort (AI Manager & Logic Manager)
    # -------------------------------------------------------------------------
    ollama_online = False
    if _AI_MANAGER_AVAILABLE and hasattr(AI_Manager, "check_connection"):
        try:
            ollama_online = AI_Manager.check_connection()
        except Exception:
            ollama_online = False

    sorted_candidates: List[Dict[str, Any]] = []

    # Case A: Live Ollama AI Screening
    if ollama_online:
        print("  [Stage 3/4] Running live Ollama AI screening model...")
        AI_Manager.screen_resumes(
            rules,
            parsed_resumes,
            resumes_file=resumes_json_path,
            results_file=AI_OUTPUT_FILE,
        )

        print("  [Stage 4/4] Validating and sorting results via Logic_manager_modules...")
        results_path = Path(AI_OUTPUT_FILE)
        
        if _LOGIC_MODULES_AVAILABLE:
            results_path_obj = ResultsPath(results_path)
            if (
                results_path_obj.validate_file_exists_func == 0
                and results_path_obj.validate_file_type_func == 0
                and results_path_obj.validate_file_empty_func == 0
            ):
                with open(results_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                results_data = ResultsData(data)
                if results_data.validate_resume_func == 0 and results_data.validate_resume_keys_func == "":
                    accepted_resume, rejected_resume, invalid_resume = Logic_Manager.filter_resume_online_func(data)
                    if _DATA_MANAGER_AVAILABLE and hasattr(Data_Manager, "outputfile_func"):
                        Data_Manager.outputfile_func(
                            accepted_resume.show_profiles,
                            rejected_resume.show_profiles,
                            invalid_resume.show_profiles,
                            str(out_dir),
                        )
                    sorted_candidates = accepted_resume.sort_score
                else:
                    print("  [!] Logic Manager detected invalid data types or missing keys.")
            else:
                print("  [!] Logic Manager could not validate output JSON file.")
        else:
            with open(results_path, "r", encoding="utf-8") as f:
                sorted_candidates = json.load(f)

    # Case B: Offline Heuristic Screening
    else:
        print("  [Stage 3/4] Ollama offline. Running Logic Manager offline screening...")
        if _LOGIC_MODULES_AVAILABLE and hasattr(Logic_Manager, "offline_screening_func"):
            offline_resumes = Logic_Manager.offline_screening_func(parsed_resumes, rules)
            print("  [Stage 4/4] Filtering and ranking offline screening results...")
            accepted_resume, rejected_resume, invalid_resume = Logic_Manager.filter_resume_offline_func(offline_resumes)
            if _DATA_MANAGER_AVAILABLE and hasattr(Data_Manager, "outputfile_func"):
                Data_Manager.outputfile_func(
                    accepted_resume.show_profiles,
                    rejected_resume.show_profiles,
                    invalid_resume.show_profiles,
                    str(out_dir),
                )
            sorted_candidates = accepted_resume.sort_score
        else:
            sorted_candidates = sorted(parsed_resumes, key=lambda c: c.get("score", 0), reverse=True)

    print(f"[Pipeline Complete] Returned {len(sorted_candidates)} ranked candidate(s).\n")
    return sorted_candidates


# =============================================================================
# Main Orchestrator (Concurrent Multi-Threading)
# =============================================================================

def start_telegram_background(pipeline_runner) -> Optional[TelegramIOManager]:
    """Starts the Telegram Bot in a daemon background thread."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("  [!] TELEGRAM_BOT_TOKEN not set in .env. Telegram bot disabled.")
        return None

    try:
        telegram_io = TelegramIOManager(token=bot_token, pipeline_runner=pipeline_runner)
        bot_thread = threading.Thread(
            target=telegram_io.start,
            name="TelegramBotDaemonThread",
            daemon=True,
        )
        bot_thread.start()
        print("  [+] Telegram Bot started concurrently in background thread.")
        return telegram_io
    except Exception as err:
        print(f"  [!] Notice: Could not start Telegram Bot in background: {err}")
        return None


def main():
    print("=" * 65)
    print("      INF1103 Team 1 - AI Resume Screening System (Phase 2)")
    print("=" * 65)

    # 1. Start Telegram Bot concurrently in background (Section 11.4 Threading)
    _ = start_telegram_background(execute_screening_pipeline)

    # 2. Start Terminal CLI in the foreground
    cli_io = CLIIOManager()

    # Pre-check Ollama connection for terminal feedback
    if _AI_MANAGER_AVAILABLE and hasattr(AI_Manager, "check_connection"):
        try:
            if not AI_Manager.check_connection():
                cli_io.display_message(
                    "ℹ️ Notice: Ollama is offline or model is missing.\n"
                    "  The system will automatically use Logic Manager offline screening."
                )
        except Exception:
            pass

    # Main Interactive CLI Loop
    config = cli_io.get_employer_inputs()
    rerun = False

    while True:
        if rerun:
            input("\nScreening complete. Press [Enter] to return to menu...")
            config = cli_io.get_employer_inputs(config)

        # Trigger shared pipeline
        ranked_candidates = execute_screening_pipeline(config)

        if not ranked_candidates:
            cli_io.display_error("No candidates were successfully evaluated.")
        else:
            cli_io.display_success("Resumes successfully screened!")
            cli_io.display_screening_results(ranked_candidates, top_n=config.get("top_n", 3))

        rerun = True


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[App] Program terminated by user. Goodbye!")
        sys.exit(0)