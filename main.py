
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from MainProg import MainProg

# Load environment variables (.env)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import I/O Manager Modules
from io_manager_modules.io_manager_cli import CLIIOManager
from io_manager_modules.io_manager_telegram import TelegramIOManager

# Safe imports for team managers (allows app to start even if dependencies are missing)
try:
    import ai_manager_modules.ai_manager as AI_Manager
    _AI_MANAGER_AVAILABLE = True
except Exception as err:
    AI_Manager = None
    _AI_MANAGER_AVAILABLE = False
    print(f"  [Notice] AI_Manager could not be loaded ({err}). Will use offline screening.")

try:
    from data_manager_modules import Data_Manager
    _DATA_MANAGER_AVAILABLE = True
except Exception as err:
    Data_Manager = None
    _DATA_MANAGER_AVAILABLE = False
    print(f"  [Notice] Data_Manager could not be loaded ({err}).")

try:
    import Logic_manager_modules.Logic_Manager as Logic_Manager
    _LOGIC_MANAGER_AVAILABLE = True
except Exception as err:
    Logic_Manager = None
    _LOGIC_MANAGER_AVAILABLE = False
    print(f"  [Notice] Logic_Manager could not be loaded ({err}).")

AI_OUTPUT_FILE = "ai_output.json"

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

    # 1. Initialize OOP Coordinator
    pipeline = MainProg(output_dir="output")

    # 2. Start Telegram Bot immediately upon CLI startup (concurrent background thread)
    _ = start_telegram_background(pipeline.run)

    # 3. Start Terminal CLI loop
    cli_io = CLIIOManager()
    if not pipeline.check_ai_connection():
        cli_io.display_message("ℹ️ Notice: Ollama offline. Using offline screening fallback.")

    config = cli_io.get_employer_inputs()
    rerun = False

    while True:
        if rerun:
            input("\nScreening complete. Press [Enter] to return to menu...")
            config = cli_io.get_employer_inputs(config)

        ranked_candidates = pipeline.run(config)

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