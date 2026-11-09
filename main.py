"""
main.py - INF1103 Phase 2 Central Coordinator
Runs CLI in the main thread and Telegram Bot in a background daemon thread concurrently.
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
    # Explicitly check working directory, /work/.env (Docker), and file directory
    for env_path in [Path.cwd() / ".env", Path("/work/.env"), Path(".env"), Path(__file__).resolve().parent / ".env"]:
        if env_path.exists():
            load_dotenv(env_path)
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
    from data_manager_modules.data_manager_side import DataManager
    _DATA_MANAGER_AVAILABLE = True
except Exception as err:
    DataManager = None
    _DATA_MANAGER_AVAILABLE = False
    print(f"  [Notice] DataManager could not be loaded ({err}).")

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
_telegram_bot_instance: Optional[TelegramIOManager] = None


# =============================================================================
# Pipeline Coordinator (Shared by both CLI and Telegram Bot)
# =============================================================================

def execute_screening_pipeline(employer_inputs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Executes the 4-stage screening pipeline.
    Bridges DataManager, AI_Manager, and Logic_manager_modules.
    """
    company_name = employer_inputs.get("company_name", "General")
    company_id = employer_inputs.get("company_id")
    rules = employer_inputs.get("business_rules", [])
    pdf_directory = employer_inputs.get("pdf_directory", "resumes")
    top_n = employer_inputs.get("top_n", 3)
    out_dir = Path(employer_inputs.get("output_directory", "output"))
    out_dir.mkdir(parents=True, exist_ok=True)

    data_mgr = DataManager() if _DATA_MANAGER_AVAILABLE else None

    print(f"\n[Pipeline] Starting screening run for '{company_name}' (ID: #{company_id}) with {len(rules)} rule(s)...")

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
    # Stage 2: Parse PDF Resumes (Data Manager - Scoped to Cloud / Company)
    # -------------------------------------------------------------------------
    print(f"  [Stage 2/4] Fetching & parsing resumes for '{company_name}' (ID: #{company_id})...")
    resumes_json_path = "resumes.json"
    parsed_resumes: List[Dict[str, Any]] = []

    if data_mgr:
        parsed_resumes = data_mgr.process_all_resumes(
            output_file=resumes_json_path, company_id=company_id
        )
    else:
        print("  [!] DataManager not available to parse resumes.")

    # Fallback to local folder if Supabase Cloud has no records for this company yet
    if not parsed_resumes and os.path.exists(pdf_directory):
        print(f"  [*] Ingesting and uploading resumes from local folder '{pdf_directory}'...")
        if data_mgr:
            data_mgr.upload_local_folder(pdf_directory, company_id=company_id)
            parsed_resumes = data_mgr.process_all_resumes(
                output_file=resumes_json_path, company_id=company_id
            )

    if not parsed_resumes:
        print(f"  [!] No valid resumes found in Cloud or in '{pdf_directory}'.")
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
        screened_results = AI_Manager.screen_resumes(
            rules,
            parsed_resumes,
            resumes_file=resumes_json_path,
            results_file=AI_OUTPUT_FILE,
        )

        # Generate and save AI Summary Report (summary.json)
        try:
            print("  [*] Generating AI Summary Report (summary.json)...")
            AI_Manager.create_summary(rules, screened_results, top_n=top_n, summary_file="summary.json")
        except Exception as err:
            print(f"  [!] Notice: AI Summary Report generation failed ({err}).")

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
                    if data_mgr and hasattr(data_mgr, "outputfile_func"):
                        data_mgr.outputfile_func(
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
            if data_mgr and hasattr(data_mgr, "outputfile_func"):
                data_mgr.outputfile_func(
                    accepted_resume.show_profiles,
                    rejected_resume.show_profiles,
                    invalid_resume.show_profiles,
                    str(out_dir),
                )
            sorted_candidates = accepted_resume.sort_score

            # Save offline summary report
            try:
                from ai_manager_modules.ai_manager_summary_builder import SummaryBuilder
                offline_summary = SummaryBuilder(rules, "offline-heuristic", top_n).build(offline_resumes)
                offline_summary["overall_summary"] = (
                    f"Screening conducted using offline heuristic keyword matching for '{company_name}'. "
                    f"Ollama AI server was offline."
                )
                with open("summary.json", "w", encoding="utf-8") as sf:
                    json.dump(offline_summary, sf, indent=2)
            except Exception:
                pass
        else:
            sorted_candidates = sorted(parsed_resumes, key=lambda c: c.get("score", 0), reverse=True)

    # Sync latest results with the Telegram bot companion
    global _telegram_bot_instance
    if _telegram_bot_instance:
        try:
            _telegram_bot_instance.display_screening_results(sorted_candidates, top_n=top_n)
        except Exception:
            pass

    print(f"[Pipeline Complete] Returned {len(sorted_candidates)} ranked candidate(s).\n")
    return sorted_candidates


# =============================================================================
# Main Orchestrator (Concurrent Multi-Threading)
# =============================================================================

def start_telegram_background() -> Optional[TelegramIOManager]:
    """Starts the Telegram Bot in a daemon background thread."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        # Check /work/.env and .env again
        for env_path in [Path.cwd() / ".env", Path("/work/.env"), Path(".env")]:
            if env_path.exists():
                try:
                    from dotenv import load_dotenv
                    load_dotenv(env_path)
                except Exception:
                    pass
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not bot_token:
        print("  [!] TELEGRAM_BOT_TOKEN not set in .env. Telegram bot disabled.")
        return None

    try:
        telegram_io = TelegramIOManager(token=bot_token)
        bot_thread = threading.Thread(
            target=telegram_io.start,
            name="TelegramBotDaemonThread",
            daemon=True,
        )
        bot_thread.start()
        print("  [+] Telegram Companion Bot started concurrently in background thread.")
        global _telegram_bot_instance
        _telegram_bot_instance = telegram_io
        return telegram_io
    except Exception as err:
        print(f"  [!] Notice: Could not start Telegram Bot in background: {err}")
        return None


def main():
    print("=" * 65)
    print("                   INF1103 Team 1 - RESUM-AI                 ")
    print("=" * 65)

    # 1. Start Telegram Bot concurrently in background (Section 11.4 Threading)
    _ = start_telegram_background()

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

            # Offer to view summary report
            if os.path.exists("summary.json"):
                print("\n  [*] Tip: AI Summary Report is saved to 'summary.json'.")
                view_sum = input("  Would you like to view the AI Summary Report now? (y/n) [Default: y]: ").strip().lower()
                if view_sum in ("", "y", "yes"):
                    cli_io.view_summary_report("summary.json")

        rerun = True


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[App] Program terminated by user. Goodbye!")
        sys.exit(0)
