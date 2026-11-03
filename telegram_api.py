import os
import re
import time
from pathlib import Path

from telegram import Update
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
        "/uploadresumes - start uploading resumes\n"
        "/doneuploading - stop uploading resumes"
    )

    def __init__(self, token: str, resume_dir: str = "resumes"):
        self.token = token
        self.resume_dir = Path(resume_dir)
        self.resume_dir.mkdir(exist_ok=True)

        self.app = ApplicationBuilder().token(self.token).build()
        self._register_handlers()

    # ---------------------------------------------------------------
    # HOW TO ADD A NEW COMMAND
    # 1. Write an async method below: async def mycommand(self, update, context)
    # 2. Register it in _register_handlers():
    #       self.app.add_handler(CommandHandler("mycommand", self.mycommand))
    # ---------------------------------------------------------------

    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("whoami", self.whoami))
        self.app.add_handler(CommandHandler("uploadresumes", self.upload_resumes))
        self.app.add_handler(CommandHandler("doneuploading", self.done_uploading))
        self.app.add_handler(MessageHandler(filters.Document.PDF, self.save_resume))

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

    # ---------------------- Resume uploading ----------------------

    async def upload_resumes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/uploadresumes - turns on upload mode for this user."""
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
        """Saves documents to the resume folder only while upload mode is ON."""
        if not context.user_data.get("uploading"):
            await update.message.reply_text("Send /uploadresumes first to start uploading resumes.")
            return

        doc = update.message.document
        user = update.effective_user

        if doc.mime_type != "application/pdf":
            await update.message.reply_text("That doesn't look like a real PDF. Please send a .pdf file.")
            return

        ext = Path(doc.file_name or "").suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            await update.message.reply_text("Only PDF files are accepted. Please send a .pdf file.")
            return

        if doc.file_size and doc.file_size > self.MAX_FILE_SIZE:
            await update.message.reply_text("File is too large (max 20 MB).")
            return

        safe_name = re.sub(r"[^\w.\- ]", "_", doc.file_name)
        save_path = self.resume_dir / f"{user.id}_{int(time.time())}_{safe_name}"

        try:
            tg_file = await doc.get_file()
            await tg_file.download_to_drive(custom_path=save_path)
        except Exception as e:
            await update.message.reply_text(f"Failed to save the file: {e}")
            return

        context.user_data["upload_count"] = context.user_data.get("upload_count", 0) + 1
        await update.message.reply_text(f"Saved: {save_path.name}")


    def run(self):
        print("Bot is running...")
        self.app.run_polling()


if __name__ == "__main__":
    telegrambot = TelegramBot("8878733622:AAFAKhS9bPJb8PpPHno1swaMY2W9yl79PQ4")
    telegrambot.run()