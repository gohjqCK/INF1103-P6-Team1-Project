"""
main.py - INF1103 RESUM-AI Server & Pipeline Coordinator
Default mode: Runs the Telegram Bot Server Console in the foreground (users interact solely via Telegram).
Legacy mode: Pass '--cli' (python main.py --cli) to run the interactive terminal CLI.
"""

import inspect
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Load environment variables (.env)
try:
    from dotenv import load_dotenv
    load_dotenv()
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
# Pipeline Coordinator (Shared by Telegram Server and Optional --cli Mode)
# =============================================================================

def execute_screening_pipeline(
    employer_inputs: Dict[str, Any],
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Executes the 4-stage screening pipeline.
    Bridges DataManager, AI_Manager, and Logic_manager_modules.
    Returns: {"ranked_candidates": [...], "summary_data": {...} | None}
    """
    def notify(stage_msg: str) -> None:
        print(f"  {stage_msg}")
        if progress_callback:
            try:
                progress_callback(stage_msg)
            except Exception:
                pass

    company_name = employer_inputs.get("company_name", "General")
    company_id = employer_inputs.get("company_id")
    rules = employer_inputs.get("business_rules", [])
    pdf_directory = employer_inputs.get("pdf_directory", "resumes")
    top_n = employer_inputs.get("top_n", 3)
    out_dir = Path(employer_inputs.get("output_directory", "output"))
    out_dir.mkdir(parents=True, exist_ok=True)

    data_mgr = DataManager() if _DATA_MANAGER_AVAILABLE else None
    cloud_ready = bool(getattr(data_mgr, "CLOUD_READY", False)) if data_mgr else False

    print(f"\n[Pipeline] Starting screening run for '{company_name}' (ID: #{company_id}) with {len(rules)} rule(s)...")

    # -------------------------------------------------------------------------
    # Stage 1: Generate AI Prompt / Keywords from Rules
    # -------------------------------------------------------------------------
    ollama_online = False
    if _AI_MANAGER_AVAILABLE and hasattr(AI_Manager, "check_connection"):
        try:
            ollama_online = AI_Manager.check_connection()
        except Exception:
            ollama_online = False

    if ollama_online:
        notify("[Stage 1/4] Generating AI prompt keywords via Ollama...")
        try:
            rules = AI_Manager.add_keywords(rules)
        except Exception as err:
            print(f"  [Stage 1/4] Notice: keyword generation skipped ({err}).")
    else:
        notify("[Stage 1/4] Ollama offline — using offline heuristic keyword mode.")

    # -------------------------------------------------------------------------
    # Stage 2: Gather & Validate Resumes (In-Memory from Telegram or DataManager)
    # -------------------------------------------------------------------------
    notify(f"[Stage 2/4] Preparing & validating resumes for '{company_name}'...")
    resumes_json_path = "resumes.json"
    parsed_resumes: List[Dict[str, Any]] = []

    preloaded_resumes = employer_inputs.get("resumes")
    if isinstance(preloaded_resumes, list) and preloaded_resumes:
        parsed_resumes = preloaded_resumes
        try:
            with open(resumes_json_path, "w", encoding="utf-8") as rf:
                json.dump(parsed_resumes, rf, indent=2, ensure_ascii=False)
        except Exception:
            pass
    elif data_mgr and cloud_ready:
        parsed_resumes = data_mgr.process_all_resumes(
            output_file=resumes_json_path, company_id=company_id
        )
    elif data_mgr and os.path.exists(pdf_directory):
        # Fallback for --cli local folder mode
        data_mgr.upload_local_folder(pdf_directory, company_id=company_id)
        parsed_resumes = data_mgr.process_all_resumes(
            output_file=resumes_json_path, company_id=company_id
        )

    if not parsed_resumes:
        print(f"  [!] No resumes found for '{company_name}' (ID: #{company_id}).")
        return {"ranked_candidates": [], "summary_data": None, "filtered_resumes": None}

    def _call_outputfile(accepted: List[Any], rejected: List[Any], invalid: List[Any]) -> None:
        if not (data_mgr and hasattr(data_mgr, "outputfile_func")):
            return
        sig = inspect.signature(data_mgr.outputfile_func)
        if "company_id" in sig.parameters:
            data_mgr.outputfile_func(accepted, rejected, invalid, str(out_dir), company_id=company_id)
        else:
            data_mgr.outputfile_func(accepted, rejected, invalid, str(out_dir))

    # -------------------------------------------------------------------------
    # Stage 3 & 4: Screen, Filter, Rank & Generate Summary
    # -------------------------------------------------------------------------
    sorted_candidates: List[Dict[str, Any]] = []
    summary_data: Optional[Dict[str, Any]] = None
    filtered_resumes: Optional[Dict[str, List[Any]]] = None

    if ollama_online:
        notify(f"[Stage 3/4] Running live Ollama AI screening on {len(parsed_resumes)} resume(s)...")
        screened_results = AI_Manager.screen_resumes(
            rules,
            parsed_resumes,
            resumes_file=resumes_json_path,
            results_file=AI_OUTPUT_FILE,
        )

        notify("[Stage 4/4] Ranking candidates & generating AI Summary Report...")
        try:
            summary_data = AI_Manager.create_summary(
                rules, screened_results, top_n=top_n, summary_file="summary.json"
            )
        except Exception as err:
            print(f"  [!] Notice: AI Summary Report generation failed ({err}).")

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
                    filtered_resumes = {
                        "accepted": accepted_resume.show_profiles,
                        "rejected": rejected_resume.show_profiles,
                        "invalid": invalid_resume.show_profiles,
                    }
                    _call_outputfile(
                        accepted_resume.show_profiles,
                        rejected_resume.show_profiles,
                        invalid_resume.show_profiles,
                    )
                    sorted_candidates = accepted_resume.sort_score
                else:
                    print("  [!] Logic Manager detected invalid data types or missing keys.")
            else:
                print("  [!] Logic Manager could not validate output JSON file.")
        else:
            with open(results_path, "r", encoding="utf-8") as f:
                sorted_candidates = json.load(f)

    else:
        notify(f"[Stage 3/4] Running offline heuristic screening on {len(parsed_resumes)} resume(s)...")
        if _LOGIC_MODULES_AVAILABLE and hasattr(Logic_Manager, "offline_screening_func"):
            offline_resumes = Logic_Manager.offline_screening_func(parsed_resumes, rules)
            notify("[Stage 4/4] Filtering, ranking & building Summary Report...")
            accepted_resume, rejected_resume, invalid_resume = Logic_Manager.filter_resume_offline_func(offline_resumes)
            filtered_resumes = {
                "accepted": accepted_resume.show_profiles,
                "rejected": rejected_resume.show_profiles,
                "invalid": invalid_resume.show_profiles,
            }
            _call_outputfile(
                accepted_resume.show_profiles,
                rejected_resume.show_profiles,
                invalid_resume.show_profiles,
            )
            sorted_candidates = accepted_resume.sort_score

            try:
                from ai_manager_modules.ai_manager_summary_builder import SummaryBuilder
                summary_data = SummaryBuilder(rules, "offline-heuristic", top_n).build(offline_resumes)
                summary_data["overall_summary"] = (
                    f"Screening conducted using offline heuristic keyword matching for '{company_name}'. "
                    f"Ollama AI server was offline."
                )
                with open("summary.json", "w", encoding="utf-8") as sf:
                    json.dump(summary_data, sf, indent=2)
            except Exception:
                pass
        else:
            sorted_candidates = sorted(parsed_resumes, key=lambda c: c.get("score", 0), reverse=True)

    print(f"[Pipeline Complete] '{company_name}' -> {len(sorted_candidates)} ranked candidate(s).\n")
    return {
        "ranked_candidates": sorted_candidates,
        "summary_data": summary_data,
        "filtered_resumes": filtered_resumes,
    }


# =============================================================================
# Startup Helpers
# =============================================================================

def _resolve_bot_token() -> Optional[str]:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        for env_path in [Path.cwd() / ".env", Path("/work/.env"), Path(".env"), Path(__file__).resolve().parent / ".env"]:
            if env_path.exists():
                try:
                    from dotenv import load_dotenv
                    load_dotenv(env_path)
                except Exception:
                    pass
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    return bot_token


def run_telegram_server() -> None:
    """Starts the RESUM-AI Telegram Bot Server Console in the foreground."""
    bot_token = _resolve_bot_token()
    data_mgr = DataManager() if _DATA_MANAGER_AVAILABLE else None
    cloud_ready = bool(getattr(data_mgr, "CLOUD_READY", False)) if data_mgr else False

    ollama_status = "Offline (will use Heuristic Fallback)"
    if _AI_MANAGER_AVAILABLE and hasattr(AI_Manager, "check_connection"):
        try:
            if AI_Manager.check_connection():
                ollama_status = "Online (Ready)"
        except Exception:
            pass

    print("=" * 65)
    print("              RESUM-AI TELEGRAM BOT SERVER CONSOLE            ")
    print("=" * 65)
    print(f"  Telegram Bot Token : {'Configured' if bot_token else 'MISSING (.env)'}")
    print(f"  Ollama AI Server   : {ollama_status}")
    print(f"  Logic Manager      : {'Loaded' if _LOGIC_MODULES_AVAILABLE else 'Unavailable'}")
    print(f"  Data Manager Mode  : {'Cloud-Ready (Supabase)' if cloud_ready else 'Cloud Stub (In-Memory)'}")
    print("=" * 65)

    if not bot_token:
        print("\n  [!] ERROR: TELEGRAM_BOT_TOKEN not set in .env or environment.")
        print("      Add TELEGRAM_BOT_TOKEN=<your_token> to .env and restart.")
        sys.exit(1)

    print("  Users interact exclusively via Telegram. Keep this window open.")
    print("  Press Ctrl+C to shut down the server.\n")

    telegram_io = TelegramIOManager(
        token=bot_token,
        data_manager=data_mgr,
        pipeline_runner=execute_screening_pipeline,
        use_cloud=cloud_ready,
    )
    telegram_io.start()


def run_legacy_cli() -> None:
    """Runs the legacy interactive terminal CLI (--cli flag) with optional background Telegram bot."""
    print("=" * 65)
    print("              INF1103 Team 1 - RESUM-AI (CLI MODE)          ")
    print("=" * 65)

    bot_token = _resolve_bot_token()
    data_mgr = DataManager() if _DATA_MANAGER_AVAILABLE else None
    cloud_ready = bool(getattr(data_mgr, "CLOUD_READY", False)) if data_mgr else False

    if bot_token:
        try:
            telegram_io = TelegramIOManager(
                token=bot_token,
                data_manager=data_mgr,
                pipeline_runner=execute_screening_pipeline,
                use_cloud=cloud_ready,
            )
            bot_thread = threading.Thread(
                target=telegram_io.start,
                name="TelegramBotDaemonThread",
                daemon=True,
            )
            bot_thread.start()
        except Exception as err:
            print(f"  [!] Could not start background Telegram Bot: {err}")

    cli_io = CLIIOManager(data_manager=data_mgr)
    config = cli_io.get_employer_inputs()
    rerun = False

    while True:
        if rerun:
            input("\nScreening complete. Press [Enter] to return to menu...")
            config = cli_io.get_employer_inputs(config)

        pipeline_output = execute_screening_pipeline(config)
        ranked_candidates = pipeline_output.get("ranked_candidates", [])

        if not ranked_candidates:
            cli_io.display_error("No candidates were successfully evaluated.")
        else:
            cli_io.display_success("Resumes successfully screened!")
            cli_io.display_screening_results(ranked_candidates, top_n=config.get("top_n", 3))

            if os.path.exists("summary.json"):
                print("\n  [*] Tip: AI Summary Report is saved to 'summary.json'.")
                view_sum = input("  Would you like to view the AI Summary Report now? (y/n) [Default: y]: ").strip().lower()
                if view_sum in ("", "y", "yes"):
                    cli_io.view_summary_report("summary.json")

        rerun = True


def main():
    if "--cli" in sys.argv:
        run_legacy_cli()
    else:
        run_telegram_server()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[Server] RESUM-AI server stopped by operator. Goodbye!")
        sys.exit(0)
