import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import hashlib
import io
import json
import os
import re
import secrets
from typing import Any, Dict, List, Optional, Tuple

from io_manager_modules.io_manager_base import BaseIOManager
from io_manager_modules.telegram_formatter import TelegramFormatter
from io_manager_modules.telegram_keyboards import TelegramKeyboards

from data_manager_modules.data_manager_supabase_handler import SupabaseHandler

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))

try:
    import telebot
    from telebot.types import CallbackQuery, Message
    _TELEBOT_AVAILABLE = True
except ImportError:
    _TELEBOT_AVAILABLE = False

try:
    import pypdf
    _PYPDF_AVAILABLE = True
except ImportError:
    _PYPDF_AVAILABLE = False


class TelegramIOManager(BaseIOManager):
    """Coordinates Telegram Bot lifecycle and routes events to helper components."""

    def __init__(
        self,
        token: Optional[str] = None,
        base_dir: str = "companies",
        data_file: str = "companies.json",
        pipeline_runner: Optional[Any] = None,
        _db_handler = SupabaseHandler(),
    ):
        if "load_dotenv" in globals():
            load_dotenv()
        self._token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        if not self._token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN not found! Please set it in your .env file or environment variables."
            )

        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._data_file = Path(data_file)
        self._companies: Dict[str, Dict[str, Any]] = self._load_companies()

        # Helper components (Composition)
        self._keyboards = TelegramKeyboards()
        self._formatter = TelegramFormatter()

        self._pipeline_runner = pipeline_runner
        self._sessions: Dict[int, Dict[str, Any]] = {}
        self._user_active_company: Dict[int, str] = {}
        self._latest_results: List[Dict[str, Any]] = []

        if not _TELEBOT_AVAILABLE:
            self._bot = None
            print("  [!] Notice: pyTelegramBotAPI not installed. Run 'pip install pyTelegramBotAPI'.")
            return

        self._bot = telebot.TeleBot(self._token, parse_mode="HTML")
        self._register_handlers()

    # -------------------------------------------------------------------------
    # BaseIOManager Contract Methods
    # -------------------------------------------------------------------------

    def display_message(self, message: str) -> None:
        print(f"[TelegramBot] {message}")

    def display_error(self, error_message: str) -> None:
        print(f"\n  [TelegramBot ERROR] {error_message}\n")

    def display_success(self, success_message: str) -> None:
        print(f"  [TelegramBot SUCCESS] {success_message}")

    def display_screening_results(
        self, ranked_candidates: List[Any], top_n: Optional[int] = None
    ) -> List[Any]:
        self._latest_results = ranked_candidates
        top_list = ranked_candidates[:top_n] if top_n else ranked_candidates
        print(f"[TelegramBot] Received {len(top_list)} candidate result(s) from screening.")
        return top_list

    def get_employer_inputs(self, rerun_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "business_rules": self._get_rules_for_active_company(),
            "pdf_directory": "resumes",
            "top_n": 3,
            "output_directory": "output",
        }

    # -------------------------------------------------------------------------
    # Storage & Session Helpers
    # -------------------------------------------------------------------------

    def _load_companies(self) -> Dict[str, Any]:
        if self._data_file.exists():
            try:
                return json.loads(self._data_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_companies(self) -> None:
        self._data_file.write_text(json.dumps(self._companies, indent=2), encoding="utf-8")

    def _get_active_company_name(self, user_id: int) -> Optional[str]:
        if user_id in self._user_active_company:
            return self._user_active_company[user_id]
        for name, info in self._companies.items():
            if user_id == info.get("owner") or user_id in info.get("members", []):
                self._user_active_company[user_id] = name
                return name
        return None

    def _company_folder(self, company_name: str) -> Path:
        folder = self._base_dir / company_name
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _company_resumes_folder(self, company_name: str) -> Path:
        folder = self._company_folder(company_name) / "resumes"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _get_rules(self, company_name: str) -> List[Dict[str, Any]]:
        rules_file = self._company_folder(company_name) / "rules.json"
        if rules_file.exists():
            try:
                return json.loads(rules_file.read_text(encoding="utf-8"))
            except Exception:
                return []
        try:
            with open("Business_Rules.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_rules(self, company_name: str, rules: List[Dict[str, Any]]) -> None:
        rules_file = self._company_folder(company_name) / "rules.json"
        rules_file.write_text(json.dumps(rules, indent=2), encoding="utf-8")
        try:
            with open("Business_Rules.json", "w", encoding="utf-8") as f:
                json.dump(rules, f, indent=2)
        except Exception:
            pass

    def _get_rules_for_active_company(self) -> List[Dict[str, Any]]:
        if self._companies:
            first = next(iter(self._companies))
            return self._get_rules(first)
        return []

    def _get_session(self, chat_id: int) -> Dict[str, Any]:
        if chat_id not in self._sessions:
            self._sessions[chat_id] = {"top_n": 3, "pending_rule_text": None}
        return self._sessions[chat_id]

    @staticmethod
    def _parse_pdf_bytes(filename: str, pdf_bytes: bytes) -> Tuple[str, str, int]:
        if not _PYPDF_AVAILABLE:
            return "valid", "OK (pypdf check skipped)", 1
        try:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            pages = len(reader.pages)
            text = "".join([p.extract_text() or "" for p in reader.pages]).strip()
            if len(text) < 200:
                return "invalid", "Resume has less than 200 characters.", pages
            if len(text) > 20000:
                return "invalid", "Resume exceeds 20,000 characters limit.", pages
            return "valid", "OK", pages
        except Exception as err:
            return "invalid", f"Corrupt or unreadable PDF: {err}", 0

    # -------------------------------------------------------------------------
    # UI Presentations
    # -------------------------------------------------------------------------

    def _send_main_dashboard(self, chat_id: int, user_id: int) -> None:
        comp_name = self._get_active_company_name(user_id)
        if not comp_name or comp_name not in self._companies:
            self._bot.send_message(
                chat_id,
                "<b>Welcome to the AI Resume Screener!</b>\n\nCreate or join a company folder to get started:",
                reply_markup=self._keyboards.auth_menu(),
            )
            return

        comp_info = self._companies[comp_name]
        rules = self._get_rules(comp_name)
        resumes = list(self._company_resumes_folder(comp_name).glob("*.pdf"))
        session = self._get_session(chat_id)

        msg = self._formatter.format_dashboard(
            company_name=comp_name,
            invite_code=comp_info.get("invite_code", "N/A"),
            rule_count=len(rules),
            resume_count=len(resumes),
            top_n=session["top_n"],
        )
        self._bot.send_message(chat_id, msg, reply_markup=self._keyboards.dashboard_menu(session["top_n"]))

    def _register_handlers(self) -> None:
        @self._bot.message_handler(commands=["start", "menu"])
        def handle_start(message: Message):
            comp_name = self._get_active_company_name(message.from_user.id)
            if not comp_name:
                self._bot.send_message(
                    message.chat.id,
                    "<b>Welcome to the AI Resume Screener!</b>\n\nCreate or join a team folder to begin:",
                    reply_markup=self._keyboards.auth_menu(),
                )
            else:
                self._send_main_dashboard(message.chat.id, message.from_user.id)

        @self._bot.message_handler(content_types=["document"])
        def handle_pdf_upload(message: Message):
            comp_name = self._get_active_company_name(message.from_user.id)
            if not comp_name:
                self._bot.reply_to(message, "⚠️ Join or create a Company Folder first using /start.")
                return

            doc = message.document
            if not doc.file_name or not doc.file_name.lower().endswith(".pdf"):
                self._bot.reply_to(message, "❌ Only <b>.pdf</b> files are accepted.")
                return

            status_msg = self._bot.reply_to(message, f"⏳ Uploading <b>{doc.file_name}</b> to Supabase...")
            try:
                # 1. Download raw file bytes from Telegram
                file_info = self._bot.get_file(doc.file_id)
                pdf_bytes = self._bot.download_file(file_info.file_path)

                # 2. Extract text and validate limits
                status, reason, pages, extracted_text = self._parse_pdf_bytes(doc.file_name, pdf_bytes)

                # 3. Upload to Supabase Storage Bucket
                public_url = self._db_handler.upload_pdf_to_storage(doc.file_name, pdf_bytes)

                # 4. Save to local folder backup
                save_path = self._company_resumes_folder(comp_name) / doc.file_name
                save_path.write_bytes(pdf_bytes)

                # 5. Register record into 'resume_files' table with all columns aligned
                if public_url:
                    self._db_handler.register_resume_file(
                        file_name=doc.file_name,
                        pdf_url=public_url,
                        company_id=None,  # Pass integer company_id if tracked in your companies.json
                        parsed_text=extracted_text,
                        pages=pages,
                        status=status,
                        invalid_reason=reason
                    )

                if status == "valid":
                    self._bot.edit_message_text(
                        f"✅ <b>{doc.file_name}</b> uploaded to Supabase ({pages}p, valid text).",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                    )
                else:
                    self._bot.edit_message_text(
                        f"⚠️ <b>{doc.file_name}</b> saved to Supabase but marked <b>INVALID</b>:\n<i>{reason}</i>",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                    )
            except Exception as err:
                self._bot.edit_message_text(f"❌ Upload failed: {err}", chat_id=message.chat.id, message_id=status_msg.message_id)

        @self._bot.message_handler(content_types=["text"])
        def handle_text_message(message: Message):
            text = (message.text or "").strip()
            # If the user typed a standalone positive integer, set Top N directly
            if text.isdigit() and int(text) > 0:
                comp_name = self._get_active_company_name(message.from_user.id)
                if comp_name:
                    val = min(int(text), 100)
                    self._get_session(message.chat.id)["top_n"] = val
                    self._bot.reply_to(message, f"🎯 <b>Top N Shortlist Limit updated to {val}!</b>")
                    self._send_main_dashboard(message.chat.id, message.from_user.id)
                    return

            self._bot.reply_to(
                message,
                "ℹ️ Tap the buttons on your dashboard or send /menu to view options."
            )

        @self._bot.callback_query_handler(func=lambda call: True)
        def handle_callbacks(call: CallbackQuery):
            chat_id = call.message.chat.id
            user_id = call.from_user.id
            data = call.data
            self._bot.answer_callback_query(call.id)

            if data == "auth_create":
                msg = self._bot.send_message(chat_id, "🏢 Enter your new <b>Company Name</b>:")
                self._bot.register_next_step_handler(msg, self._step_create_company_name)
                return

            if data == "auth_join":
                msg = self._bot.send_message(chat_id, "🔑 Enter your team's <b>Invite Code</b>:")
                self._bot.register_next_step_handler(msg, self._step_join_company_code)
                return

            if data == "menu_switch":
                self._bot.send_message(chat_id, "Select an option:", reply_markup=self._keyboards.auth_menu())
                return

            comp_name = self._get_active_company_name(user_id)
            if not comp_name:
                self._bot.send_message(chat_id, "Please authenticate:", reply_markup=self._keyboards.auth_menu())
                return

            if data == "menu_main":
                self._send_main_dashboard(chat_id, user_id)

            elif data == "menu_rules":
                msg = self._formatter.format_rules_list(comp_name, self._get_rules(comp_name))
                self._bot.send_message(chat_id, msg, reply_markup=self._keyboards.rules_menu())

            elif data == "rule_add":
                msg = self._bot.send_message(chat_id, "✏️ Enter rule requirement text (5-300 characters):")
                self._bot.register_next_step_handler(msg, self._step_add_rule_text, comp_name)

            elif data.startswith("rule_prio:"):
                prio = data.split(":", 1)[1]
                session = self._get_session(chat_id)
                rule_text = session.get("pending_rule_text")
                if rule_text:
                    rules = self._get_rules(comp_name)
                    rules.append({"text": rule_text, "priority": prio})
                    self._save_rules(comp_name, rules)
                    session["pending_rule_text"] = None
                    self._bot.send_message(chat_id, f"✅ Added Rule: <b>[{prio.upper()}]</b> {rule_text}")
                msg = self._formatter.format_rules_list(comp_name, self._get_rules(comp_name))
                self._bot.send_message(chat_id, msg, reply_markup=self._keyboards.rules_menu())

            elif data == "rule_del_menu":
                rules = self._get_rules(comp_name)
                if not rules:
                    self._bot.send_message(chat_id, "ℹ️ No rules to delete.")
                    return
                self._bot.send_message(chat_id, "Tap a rule below to delete it:", reply_markup=self._keyboards.delete_rules_menu(rules))

            elif data.startswith("rule_del:"):
                idx = int(data.split(":", 1)[1])
                rules = self._get_rules(comp_name)
                if 1 <= idx <= len(rules):
                    removed = rules.pop(idx - 1)
                    self._save_rules(comp_name, rules)
                    self._bot.send_message(chat_id, f"🗑 Removed: <b>{removed.get('text', '')}</b>")
                msg = self._formatter.format_rules_list(comp_name, self._get_rules(comp_name))
                self._bot.send_message(chat_id, msg, reply_markup=self._keyboards.rules_menu())

            elif data == "rule_clear":
                self._save_rules(comp_name, [])
                self._bot.send_message(chat_id, "🧹 All business rules cleared.")
                self._send_main_dashboard(chat_id, user_id)

            elif data == "menu_resumes":
                resumes = list(self._company_resumes_folder(comp_name).glob("*.pdf"))
                text = (
                    f"📁 <b>Resumes in {comp_name} ({len(resumes)}):</b>\n\n"
                    + "\n".join(f"• <b>{r.name}</b>" for r in resumes)
                    if resumes
                    else "📁 <b>No resumes in your folder.</b>\nDrag & drop PDF files to upload!"
                )
                self._bot.send_message(chat_id, text, reply_markup=self._keyboards.back_to_dashboard())

            elif data == "menu_topn":
                curr_n = self._get_session(chat_id).get("top_n", 3)
                self._bot.send_message(
                    chat_id,
                    f"🎯 <b>Select Candidate Limit (Top N):</b>\n\n"
                    f"Current limit: <b>{curr_n}</b>\n\n"
                    f"• Tap a quick preset below, OR\n"
                    f"• Tap <b>✏️ Custom Number</b> to type any custom limit (e.g. 2, 7, 15):",
                    reply_markup=self._keyboards.top_n_menu(),
                )

            elif data == "set_topn_custom":
                msg = self._bot.send_message(
                    chat_id,
                    "✏️ <b>Enter Custom Top N Limit:</b>\n"
                    "Please send any positive whole number (e.g. <code>2</code>, <code>7</code>, <code>15</code>):"
                )
                self._bot.register_next_step_handler(msg, self._step_set_custom_topn)

            elif data.startswith("set_topn:"):
                val = int(data.split(":", 1)[1])
                self._get_session(chat_id)["top_n"] = val
                self._bot.send_message(chat_id, f"🎯 <b>Top N Shortlist Limit set to {val}!</b>")
                self._send_main_dashboard(chat_id, user_id)

            elif data == "menu_screen":
                self._trigger_screening(chat_id, comp_name)

            elif data == "menu_results":
                self._send_results_view(chat_id, comp_name)

            elif data == "menu_summary":
                self._send_summary_breakdown(chat_id, comp_name)

            elif data.startswith("cand_view:"):
                idx = int(data.split(":", 1)[1])
                if 1 <= idx <= len(self._latest_results):
                    msg = self._formatter.format_candidate_profile(self._latest_results[idx - 1], idx)
                    self._bot.send_message(chat_id, msg, reply_markup=self._keyboards.candidate_profile_menu(idx))

            elif data.startswith("cand_pdf:"):
                idx = int(data.split(":", 1)[1])
                self._send_candidate_pdf(chat_id, comp_name, idx)

    # -------------------------------------------------------------------------
    # Conversational Step Handlers
    # -------------------------------------------------------------------------

    def _step_set_custom_topn(self, message: Message) -> None:
        text = (message.text or "").strip()
        if not text.isdigit() or int(text) < 1:
            msg = self._bot.reply_to(
                message,
                "❌ <b>Invalid input!</b> Please send a positive number greater than 0 (e.g. 2, 5, 10):"
            )
            self._bot.register_next_step_handler(msg, self._step_set_custom_topn)
            return

        val = min(int(text), 100)
        self._get_session(message.chat.id)["top_n"] = val
        self._bot.send_message(message.chat.id, f"✅ <b>Top N Shortlist Limit set to {val}!</b>")
        self._send_main_dashboard(message.chat.id, message.from_user.id)

    def _step_create_company_name(self, message: Message) -> None:
        name = (message.text or "").strip()
        if len(name) < 2:
            self._bot.reply_to(message, "❌ Name too short. Use /start to try again.")
            return
        msg = self._bot.reply_to(message, f"🔒 Set a <b>Passcode</b> for <b>{name}</b> (min 4 characters):")
        self._bot.register_next_step_handler(msg, self._step_create_company_passcode, name)

    def _step_create_company_passcode(self, message: Message, name: str) -> None:
        passcode = (message.text or "").strip()
        if len(passcode) < 4:
            self._bot.reply_to(message, "❌ Passcode must be at least 4 characters.")
            return
        prefix = "".join(c for c in name.upper() if c.isalnum())[:4] or "COMP"
        invite_code = f"{prefix}-{secrets.randbelow(9000) + 1000}"
        self._companies[name] = {
            "owner": message.from_user.id,
            "invite_code": invite_code,
            "passcode_hash": hashlib.sha256(passcode.encode("utf-8")).hexdigest(),
            "members": [message.from_user.id],
        }
        self._save_companies()
        self._user_active_company[message.from_user.id] = name
        self._bot.send_message(
            message.chat.id,
            f"🎉 <b>Company Created!</b>\n🏢 <b>{name}</b>\n🔑 Invite Code: <code>{invite_code}</code>",
        )
        self._send_main_dashboard(message.chat.id, message.from_user.id)

    def _step_join_company_code(self, message: Message) -> None:
        code = (message.text or "").strip().upper()
        target = next((n for n, i in self._companies.items() if i.get("invite_code") == code), None)
        if not target:
            self._bot.reply_to(message, "❌ Invalid Invite Code. Use /start to try again.")
            return
        msg = self._bot.reply_to(message, f"🔒 Enter Passcode for <b>{target}</b>:")
        self._bot.register_next_step_handler(msg, self._step_join_company_passcode, target)

    def _step_join_company_passcode(self, message: Message, comp_name: str) -> None:
        passcode = (message.text or "").strip()
        target_hash = self._companies[comp_name].get("passcode_hash")
        if hashlib.sha256(passcode.encode("utf-8")).hexdigest() != target_hash:
            self._bot.reply_to(message, "❌ Incorrect Passcode. Use /start to try again.")
            return

        if message.from_user.id not in self._companies[comp_name]["members"]:
            self._companies[comp_name]["members"].append(message.from_user.id)
            self._save_companies()

        self._user_active_company[message.from_user.id] = comp_name
        self._bot.send_message(message.chat.id, f"✅ Joined <b>{comp_name}</b>!")
        self._send_main_dashboard(message.chat.id, message.from_user.id)

    def _step_add_rule_text(self, message: Message, comp_name: str) -> None:
        text = (message.text or "").strip()
        if len(text) < 5 or len(text) > 300:
            self._bot.reply_to(message, "❌ Rule must be 5-300 characters.")
            return
        self._get_session(message.chat.id)["pending_rule_text"] = text
        self._bot.send_message(
            message.chat.id,
            f"Select priority weight for:\n<i>\"{text}\"</i>",
            reply_markup=self._keyboards.priority_selection_menu(),
        )

    # -------------------------------------------------------------------------
    # Pipeline & Presentation Delegates
    # -------------------------------------------------------------------------

    def _trigger_screening(self, chat_id: int, comp_name: str) -> None:
        rules = self._get_rules(comp_name)
        if not rules:
            self._bot.send_message(chat_id, "⚠️ Configure at least one rule before screening!")
            return

        resumes = list(self._company_resumes_folder(comp_name).glob("*.pdf"))
        if not resumes:
            self._bot.send_message(chat_id, "⚠️ No PDF resumes found! Drag and drop files into chat.")
            return

        session = self._get_session(chat_id)
        employer_inputs = {
            "business_rules": rules,
            "pdf_directory": str(self._company_resumes_folder(comp_name)),
            "top_n": session.get("top_n", 3),
        }

        # If connected to main pipeline runner:
        if self._pipeline_runner and callable(self._pipeline_runner):
            wait_msg = self._bot.send_message(chat_id, "⏳ <b>Sending employer data to pipeline for screening...</b>")
            try:
                # Orchestrator handles Data_Manager and AI_Manager
                results = self._pipeline_runner(employer_inputs)
                self.display_screening_results(results, session.get("top_n", 3))
                self._bot.edit_message_text(
                    f"✅ <b>AI Screening Complete!</b>\nReceived {len(results)} evaluated candidate(s).",
                    chat_id=chat_id,
                    message_id=wait_msg.message_id
                )
                self._send_results_view(chat_id, comp_name)
            except Exception as err:
                self._bot.edit_message_text(f"❌ Screening failed: {err}", chat_id=chat_id, message_id=wait_msg.message_id)
        else:
            # Standalone mode: cleanly confirms data is packaged for the other managers
            self._bot.send_message(
                chat_id,
                f"📋 <b>Employer Inputs Packaged for Screening:</b>\n\n"
                f"• <b>Company:</b> {comp_name}\n"
                f"• <b>Configured Rules:</b> {len(rules)}\n"
                f"• <b>Uploaded Resumes:</b> {len(resumes)} file(s)\n"
                f"• <b>Top N Shortlist Limit:</b> {session.get('top_n', 3)}\n\n"
                f"<i>ℹ️ Ready for Data_Manager and AI_Manager when launched via main.py coordinator.</i>"
            )

    def _send_results_view(self, chat_id: int, comp_name: str) -> None:
        if not self._latest_results:
            self._bot.send_message(chat_id, "ℹ️ No screening results yet. Run screening first!")
            return

        session = self._get_session(chat_id)
        ranked = self._latest_results[: session.get("top_n", 3)]
        msg = self._formatter.format_results_overview(comp_name, ranked)
        self._bot.send_message(chat_id, msg, reply_markup=self._keyboards.results_menu(len(ranked)))

    def _send_candidate_pdf(self, chat_id: int, comp_name: str, idx: int) -> None:
        if not self._latest_results or idx > len(self._latest_results):
            self._bot.send_message(chat_id, "Candidate not found.")
            return

        filename = self._latest_results[idx - 1].get("file", "")
        pdf_path = self._company_resumes_folder(comp_name) / filename
        if not pdf_path.exists():
            pdf_path = Path("resumes") / filename

        if pdf_path.exists():
            with open(pdf_path, "rb") as f:
                self._bot.send_document(chat_id, f, caption=f"📄 Resume: <b>{filename}</b>")
        else:
            self._bot.send_message(chat_id, f"❌ File '{filename}' not found.")

    def _send_summary_breakdown(self, chat_id: int, comp_name: str) -> None:
        if not self._latest_results:
            self._bot.send_message(chat_id, "ℹ️ No results to summarize. Run screening first!")
            return
        rules = self._get_rules(comp_name)
        msg = self._formatter.format_summary_report(comp_name, rules, self._latest_results)
        self._bot.send_message(chat_id, msg, reply_markup=self._keyboards.back_to_dashboard())

    # -------------------------------------------------------------------------
    # Polling Starter
    # -------------------------------------------------------------------------

    def start(self) -> None:
        """Starts the Telegram bot polling loop."""
        if not self._bot:
            print("[TelegramBot] Error: bot not initialized.")
            return
        print("  [TelegramBot] Interactive bot started with inline keyboards...")
        self._bot.infinity_polling(timeout=20, long_polling_timeout=10)


if __name__ == "__main__":
    telegram_io = TelegramIOManager()
    telegram_io.start()