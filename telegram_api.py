import json
import os
import re
import time
from pathlib import Path

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


class TelegramBot:
    ALLOWED_EXTENSIONS = {".pdf"}
    MAX_FILE_SIZE = 20 * 1024 * 1024  # Telegram bots can only download files up to 20 MB

    HELP_TEXT = (
        "Available commands:\n"
        "/start - greet the bot\n"
        "/help - show this message\n"
        "/whoami - show your Telegram info\n"
        "/createcompany <name> - create a company\n"
        "/addmember <telegram_id> - add a user to your company (owner only)\n"
        "/mycompany - show your company and its members\n"
        "/uploadresumes - start uploading resumes\n"
        "/doneuploading - stop uploading resumes\n"
        "/listresumes - list your company's uploaded resumes"
    )

    def __init__(self, token: str, base_dir: str = "companies", data_file: str = "companies.json"):
        self.token = token
        self.base_dir = Path(base_dir)  # use "." to get <company name>/resumes right next to the script
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.data_file = Path(data_file)

        # {company_name: {"owner": telegram_id, "members": {"telegram_id": "first name"}}}
        self.companies = self._load()

        self.app = ApplicationBuilder().token(self.token).build()
        self._register_handlers()

    # ---------------------- Storage helpers ----------------------

    def _load(self) -> dict:
        if self.data_file.exists():
            try:
                return json.loads(self.data_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _save(self):
        self.data_file.write_text(json.dumps(self.companies, indent=2), encoding="utf-8")

    def _company_of(self, user_id: int):
        """Returns the company name a user belongs to, or None."""
        for name, info in self.companies.items():
            if str(user_id) in info["members"]:
                return name
        return None

    def _resume_folder(self, company: str) -> Path:
        folder = self.base_dir / company / "resumes"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    @staticmethod
    def _clean_company_name(raw: str):
        """Letters, numbers, spaces, - and _ only (safe to use as a folder name)."""
        name = re.sub(r"\s+", " ", raw).strip()
        return name if re.fullmatch(r"[\w \-]{1,40}", name) else None

    # ---------------------- Handlers ----------------------

    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("whoami", self.whoami))
        self.app.add_handler(CommandHandler("createcompany", self.create_company))
        self.app.add_handler(CommandHandler("addmember", self.add_member))
        self.app.add_handler(CommandHandler("mycompany", self.my_company))
        self.app.add_handler(CommandHandler("uploadresumes", self.upload_resumes))
        self.app.add_handler(CommandHandler("doneuploading", self.done_uploading))
        self.app.add_handler(CommandHandler("listresumes", self.list_resumes))
        self.app.add_handler(MessageHandler(filters.Document.ALL, self.save_resume))

        # Plain text that isn't a command (keep this last)
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

    # ---------------------- Basic commands ----------------------

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(self.HELP_TEXT)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(self.HELP_TEXT)

    async def whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        await update.message.reply_text(
            f"ID: {user.id}\n"
            f"Name: {user.first_name}\n"
            f"Username: @{user.username}"
        )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"You said: {update.message.text}\n(Try /help for commands)"
        )

    # ---------------------- Company commands ----------------------

    async def create_company(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/createcompany <name>"""
        user = update.effective_user

        existing = self._company_of(user.id)
        if existing:
            await update.message.reply_text(f"You're already in the company '{existing}'.")
            return

        name = self._clean_company_name(" ".join(context.args))
        if name is None:
            await update.message.reply_text(
                "Usage: /createcompany <name>\n"
                "Use 1-40 letters, numbers, spaces, - or _ only."
            )
            return

        if any(n.lower() == name.lower() for n in self.companies):
            await update.message.reply_text("That company name is already taken.")
            return

        self.companies[name] = {
            "owner": user.id,
            "members": {str(user.id): user.first_name},
        }
        self._save()
        self._resume_folder(name)  # creates <base_dir>/<name>/resumes

        await update.message.reply_text(
            f"Company '{name}' created. You're the owner.\n"
            "Add people with /addmember <telegram_id>.\n"
            "(They must open this bot and send /start first.)"
        )

    async def add_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/addmember <telegram_id> - owner only."""
        user = update.effective_user

        company = self._company_of(user.id)
        if not company:
            await update.message.reply_text("You're not in a company. Use /createcompany first.")
            return

        # Remove this check if you want any member to be able to add people
        if self.companies[company]["owner"] != user.id:
            await update.message.reply_text("Only the company owner can add members.")
            return

        if len(context.args) != 1 or not context.args[0].isdigit():
            await update.message.reply_text(
                "Usage: /addmember <telegram_id>\n"
                "Ask them to send /whoami to this bot to get their ID."
            )
            return

        new_id = int(context.args[0])

        other = self._company_of(new_id)
        if other:
            await update.message.reply_text(f"That user is already in the company '{other}'.")
            return

        # Look the user up (only works if they've started the bot)
        try:
            chat = await context.bot.get_chat(new_id)
        except TelegramError:
            await update.message.reply_text(
                "I couldn't find that user. Ask them to open this bot and send /start first, "
                "then try again."
            )
            return

        name = chat.first_name or chat.username or str(new_id)
        self.companies[company]["members"][str(new_id)] = name
        self._save()

        # Greet the new member
        try:
            await context.bot.send_message(
                chat_id=new_id,
                text=f"Hi {name}. You have been added to {company}.\n\n{self.HELP_TEXT}",
            )
        except TelegramError:
            await update.message.reply_text(
                f"{name} was added, but I couldn't send them the greeting."
            )
            return

        await update.message.reply_text(f"{name} has been added to '{company}'.")

    async def my_company(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/mycompany - show company name and members."""
        company = self._company_of(update.effective_user.id)
        if not company:
            await update.message.reply_text("You're not in a company. Use /createcompany first.")
            return

        info = self.companies[company]
        lines = []
        for uid, name in info["members"].items():
            role = " (owner)" if int(uid) == info["owner"] else ""
            lines.append(f"- {name}{role}")

        await update.message.reply_text(f"Company: {company}\nMembers:\n" + "\n".join(lines))

    # ---------------------- Resume uploading ----------------------

    async def upload_resumes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/uploadresumes - turns on upload mode for this user."""
        if not self._company_of(update.effective_user.id):
            await update.message.reply_text("Join or create a company first (/createcompany).")
            return

        context.user_data["uploading"] = True
        context.user_data["upload_count"] = 0
        await update.message.reply_text(
            "Upload mode ON. Send your resumes as PDF files.\n"
            "Send /doneuploading when you're finished."
        )

    async def done_uploading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/doneuploading - turns off upload mode for this user."""
        if not context.user_data.get("uploading"):
            await update.message.reply_text("You're not in upload mode. Use /uploadresumes first.")
            return

        count = context.user_data.get("upload_count", 0)
        context.user_data["uploading"] = False
        await update.message.reply_text(f"Upload mode OFF. {count} resume(s) saved.")

    async def save_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Saves PDFs to <company>/resumes only while upload mode is ON."""
        user = update.effective_user
        company = self._company_of(user.id)

        if not company:
            await update.message.reply_text("Join or create a company first (/createcompany).")
            return

        if not context.user_data.get("uploading"):
            await update.message.reply_text("Send /uploadresumes first to start uploading resumes.")
            return

        doc = update.message.document

        ext = Path(doc.file_name or "").suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            await update.message.reply_text("Only PDF files are accepted. Please send a .pdf file.")
            return

        if doc.file_size and doc.file_size > self.MAX_FILE_SIZE:
            await update.message.reply_text("File is too large (max 20 MB).")
            return

        # Saved as <user_id>_<timestamp>_<original name> so files never overwrite each other
        safe_name = re.sub(r"[^\w.\- ]", "_", doc.file_name)
        save_path = self._resume_folder(company) / f"{user.id}_{int(time.time())}_{safe_name}"

        try:
            tg_file = await doc.get_file()
            await tg_file.download_to_drive(custom_path=save_path)
        except Exception as e:
            await update.message.reply_text(f"Failed to save the file: {e}")
            return

        context.user_data["upload_count"] = context.user_data.get("upload_count", 0) + 1
        await update.message.reply_text(f"Saved: {safe_name}")

    async def list_resumes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/listresumes - shows file names without the user id and timestamp."""
        company = self._company_of(update.effective_user.id)
        if not company:
            await update.message.reply_text("You're not in a company. Use /createcompany first.")
            return

        files = sorted(self._resume_folder(company).glob("*.pdf"))
        if not files:
            await update.message.reply_text("No resumes uploaded yet.")
            return

        # "123456_1700000000_john_cv.pdf" -> "john_cv.pdf"
        names = [f.name.split("_", 2)[-1] for f in files]
        text = f"Resumes for {company} ({len(names)}):\n" + "\n".join(
            f"{i}. {n}" for i, n in enumerate(names, 1)
        )
        await update.message.reply_text(text)

    # ---------------------- Run ----------------------

    def run(self):
        print("Bot is running...")
        self.app.run_polling()


if __name__ == "__main__":
    telegrambot = TelegramBot("8878733622:AAFAKhS9bPJb8PpPHno1swaMY2W9yl79PQ4")
    telegrambot.run()