import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from main_modules.MainProg import MainProg
from io_manager_modules.io_manager_telegram import TelegramIOManager


def main():
    print("=" * 65)
    print("      RESUM-AI Team 1 - AI Resume Screening System (Phase 2)")
    print("=" * 65)

    # Check if Telegram Token is in the env file
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("  [!] TELEGRAM_BOT_TOKEN is not set in .env - cannot start the bot.")
        sys.exit(1)

    # 2. OOP coordinator (AI -> Data -> Logic managers)
    pipeline = MainProg(output_dir="output")
    if not pipeline.check_ai_connection():
        print("  [Notice] Ollama offline. Screening will use the offline fallback.")

    # 3. Runs in telegram bot in the main thread
    bot = TelegramIOManager(
        token=token,
        pipeline_runner=pipeline.run,
        ai_status_checker=pipeline.check_ai_connection,
    )
    bot.start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[App] Program terminated by user. Goodbye!")
        sys.exit(0)
