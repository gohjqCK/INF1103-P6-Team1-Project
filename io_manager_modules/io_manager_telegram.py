import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import hashlib
import json
import os
import secrets
from typing import Any, Dict, List, Optional

from io_manager_modules.io_manager_base import BaseIOManager
from io_manager_modules.telegram_formatter import TelegramFormatter
from io_manager_modules.telegram_keyboards import TelegramKeyboards

from data_manager_modules.data_manager_side import DataManager

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


class TelegramIOManager(BaseIOManager):
    """Streamlined Telegram Companion Bot for Company Creation/Joining, Cloud PDF Resume Uploads, and Viewing Results/Summary."""

    def __init__(
        self,
        token: Optional[str] = None,
        base_dir: str = "companies",
        data_file: str = "companies.json",
        data_manager: Optional[DataManager] = None,
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
        self._data_manager = data_manager or DataManager()
        self._db_handler = self._data_manager.db_handler

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
        print(f"[TelegramBot] Synced {len(top_list)} candidate result(s) from screening.")
        return top_list

    def get_employer_inputs(self, rerun_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "business_rules": self._get_rules(),
            "pdf_directory": "resumes",
            "top_n": 3,
            "output_directory": "output",
        }

    # -------------------------------------------------------------------------
    # Company & Cloud Storage Helpers
    # -------------------------------------------------------------------------

    def _load_companies(self) -> Dict[str, Dict[str, Any]]:
        companies: Dict[str, Dict[str, Any]] = {}
        if self._data_file.exists():
            try:
                companies = json.loads(self._data_file.read_text(encoding="utf-8"))
            except Exception:
                companies = {}

        # Ensure every company has a unique integer company_id for Supabase
        changed = False
        used_ids = {
            int(info["company_id"])
            for info in companies.values()
            if isinstance(info, dict) and isinstance(info.get("company_id"), int)
        }
        next_id = 101
        for name, info in companies.items():
            if isinstance(info, dict) and not isinstance(info.get("company_id"), int):
                while next_id in used_ids:
                    next_id += 1
                info["company_id"] = next_id
                used_ids.add(next_id)
                changed = True

        if changed:
            self._data_file.write_text(json.dumps(companies, indent=2), encoding="utf-8")
        return companies

    def _save_companies(self) -> None:
        self._data_file.write_text(json.dumps(self._companies, indent=2), encoding="utf-8")

    def _next_company_id(self) -> int:
        self._companies = self._load_companies()
        existing = [
            int(info["company_id"])
            for info in self._companies.values()
            if isinstance(info, dict) and isinstance(info.get("company_id"), int)
        ]
        return (max(existing) + 1) if existing else 101

    def _get_active_company_name(self, user_id: int) -> Optional[str]:
        self._companies = self._load_companies()
        if user_id in self._user_active_company:
            active = self._user_active_company[user_id]
            if active in self._companies:
                return active
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

    def _get_cloud_and_local_resumes(self, company_name: str, company_id: Optional[int]) -> List[Dict[str, Any]]:
        """Returns combined list of resumes uploaded for this company in Supabase Cloud and local backup."""
        records_by_name: Dict[str, Dict[str, Any]] = {}
        try:
            cloud_files = self._db_handler.fetch_resume_files(company_id=company_id)
            for row in cloud_files:
                fname = row.get("file_name")
                if fname:
                    records_by_name[fname] = {
                        "file_name": fname,
                        "status": row.get("status", "valid"),
                        "pages": row.get("pages", 0),
                        "source": "Supabase Cloud",
                    }
        except Exception:
            pass

        for pdf_path in sorted(self._company_resumes_folder(company_name).glob("*.pdf")):
            if pdf_path.name not in records_by_name:
                records_by_name[pdf_path.name] = {
                    "file_name": pdf_path.name,
                    "status": "valid",
                    "pages": 0,
                    "source": "Local Folder",
                }
        return list(records_by_name.values())

    def _get_rules(self) -> List[Dict[str, Any]]:
        try:
            with open("Business_Rules.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _load_latest_results_from_disk(self) -> List[Dict[str, Any]]:
        """Loads screening results from memory, latest output/filtered_resume_*.json, or ai_output.json."""
        if self._latest_results:
            return self._latest_results

        # 1. Check output/ folder for newest filtered_resume_*.json
        output_dir = Path("output")
        if output_dir.exists():
            files = sorted(output_dir.glob("filtered_resume_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            for fpath in files:
                try:
                    data = json.loads(fpath.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        accepted: List[Dict[str, Any]] = []
                        for item in data:
                            if isinstance(item, dict) and "accepted" in item:
                                accepted.extend(item["accepted"])
                        if accepted:
                            self._latest_results = accepted
                            return accepted
                except Exception:
                    continue

        # 2. Fallback to ai_output.json
        ai_out = Path("ai_output.json")
        if ai_out.exists():
            try:
                data = json.loads(ai_out.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    accepted = [
                        c for c in data
                        if isinstance(c, dict) and c.get("outcome") not in ("rejected", "invalid") and (c.get("score") or 0) > 0
                    ]
                    accepted.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
                    if accepted:
                        self._latest_results = accepted
                        return accepted
            except Exception:
                pass

        return []

    def _load_summary_json(self) -> Optional[Dict[str, Any]]:
        """Loads summary.json generated by AIManager.create_summary() if present."""
        summary_path = Path("summary.json")
        if summary_path.exists():
            try:
                data = json.loads(summary_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "totals" in data:
                    return data
            except Exception:
                pass
        return None

    # -------------------------------------------------------------------------
    # UI Presentations
    # -------------------------------------------------------------------------

    def _send_main_dashboard(self, chat_id: int, user_id: int) -> None:
        comp_name = self._get_active_company_name(user_id)
        if not comp_name or comp_name not in self._companies:
            self._bot.send_message(
                chat_id,
                "<b>Welcome to RESUM-AI (Cloud Upload Companion)!</b>\n\n"
                "Create or join a company folder to upload PDF resumes and view screening reports:",
                reply_markup=self._keyboards.auth_menu(),
            )
            return

        comp_info = self._companies[comp_name]
        comp_id = comp_info.get("company_id", 101)
        resumes = self._get_cloud_and_local_resumes(comp_name, comp_id)

        msg = self._formatter.format_dashboard(
            company_name=comp_name,
            invite_code=comp_info.get("invite_code", "N/A"),
            company_id=comp_id,
            resume_count=len(resumes),
        )
        self._bot.send_message(chat_id, msg, reply_markup=self._keyboards.dashboard_menu())

    def _register_handlers(self) -> None:
        @self._bot.message_handler(commands=["start", "menu"])
        def handle_start(message: Message):
            comp_name = self._get_active_company_name(message.from_user.id)
            if not comp_name:
                self._bot.send_message(
                    message.chat.id,
                    "<b>Welcome to RESUM-AI (Cloud Upload Companion)!</b>\n\n"
                    "Create or join a company folder to begin uploading resumes:",
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

            comp_info = self._companies.get(comp_name, {})
            comp_id = comp_info.get("company_id", 101)

            status_msg = self._bot.reply_to(
                message,
                f"⏳ Uploading <b>{doc.file_name}</b> to Supabase Cloud for <b>{comp_name}</b>...",
            )
            try:
                # 1. Download raw file bytes from Telegram
                file_info = self._bot.get_file(doc.file_id)
                pdf_bytes = self._bot.download_file(file_info.file_path)

                # 2. Save local backup in companies/<comp_name>/resumes/
                save_path = self._company_resumes_folder(comp_name) / doc.file_name
                save_path.write_bytes(pdf_bytes)

                # 3. Delegate parsing + Supabase Storage & DB upload to DataManager
                upload_info = self._data_manager.upload_resume_bytes(
                    file_name=doc.file_name,
                    pdf_bytes=pdf_bytes,
                    company_id=comp_id,
                )

                status = upload_info.get("status", "valid")
                pages = upload_info.get("pages", 0)
                reason = upload_info.get("reason", "")

                if status == "valid":
                    self._bot.edit_message_text(
                        f"✅ <b>{doc.file_name}</b> uploaded to Supabase Cloud!\n"
                        f"🏢 Company: <b>{comp_name}</b> <code>(ID: #{comp_id})</code>\n"
                        f"📄 Pages: <b>{pages}</b> | Status: <b>VALID</b>",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                    )
                else:
                    self._bot.edit_message_text(
                        f"⚠️ <b>{doc.file_name}</b> uploaded to Supabase Cloud, but marked <b>INVALID</b>:\n"
                        f"<i>{reason}</i>",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                    )
            except Exception as err:
                self._bot.edit_message_text(
                    f"❌ Upload failed: {err}",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                )

        @self._bot.message_handler(content_types=["text"])
        def handle_text_message(message: Message):
            self._bot.reply_to(
                message,
                "📤 Drag & drop a <b>.pdf</b> resume here to upload it to Supabase Cloud, "
                "or send /menu to open your company dashboard.",
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

            elif data == "menu_resumes":
                comp_id = self._companies.get(comp_name, {}).get("company_id", 101)
                resumes = self._get_cloud_and_local_resumes(comp_name, comp_id)
                if resumes:
                    lines = [f"📁 <b>Uploaded Resumes for {comp_name} ({len(resumes)}):</b>\n"]
                    for r in resumes:
                        badge = "✅" if r.get("status") == "valid" else "⚠️"
                        pages_str = f" ({r['pages']}p)" if r.get("pages") else ""
                        lines.append(f"{badge} <b>{r['file_name']}</b>{pages_str} — <i>{r['source']}</i>")
                    text = "\n".join(lines)
                else:
                    text = (
                        f"📁 <b>No resumes uploaded for {comp_name} yet.</b>\n\n"
                        f"Drag & drop PDF files directly into this chat to upload them to Supabase Cloud!"
                    )
                self._bot.send_message(chat_id, text, reply_markup=self._keyboards.back_to_dashboard())

            elif data == "menu_results":
                self._send_results_view(chat_id, comp_name)

            elif data == "menu_summary":
                self._send_summary_breakdown(chat_id, comp_name)

            elif data.startswith("cand_view:"):
                idx = int(data.split(":", 1)[1])
                results = self._load_latest_results_from_disk()
                if 1 <= idx <= len(results):
                    msg = self._formatter.format_candidate_profile(results[idx - 1], idx)
                    self._bot.send_message(chat_id, msg, reply_markup=self._keyboards.candidate_profile_menu(idx))

            elif data.startswith("cand_pdf:"):
                idx = int(data.split(":", 1)[1])
                self._send_candidate_pdf(chat_id, comp_name, idx)

    # -------------------------------------------------------------------------
    # Conversational Step Handlers (Company Creation & Joining)
    # -------------------------------------------------------------------------

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
            self._bot.reply_to(message, "❌ Passcode must be at least 4 characters. Use /start to try again.")
            return
        prefix = "".join(c for c in name.upper() if c.isalnum())[:4] or "COMP"
        invite_code = f"{prefix}-{secrets.randbelow(9000) + 1000}"
        comp_id = self._next_company_id()

        self._companies[name] = {
            "company_id": comp_id,
            "owner": message.from_user.id,
            "invite_code": invite_code,
            "passcode_hash": hashlib.sha256(passcode.encode("utf-8")).hexdigest(),
            "members": [message.from_user.id],
        }
        self._save_companies()
        self._user_active_company[message.from_user.id] = name
        self._bot.send_message(
            message.chat.id,
            f"🎉 <b>Company Created!</b>\n"
            f"🏢 <b>{name}</b> <code>(ID: #{comp_id})</code>\n"
            f"🔑 Invite Code: <code>{invite_code}</code>\n\n"
            f"<i>Share this Invite Code and Passcode with your team or use it in the CLI!</i>",
        )
        self._send_main_dashboard(message.chat.id, message.from_user.id)

    def _step_join_company_code(self, message: Message) -> None:
        self._companies = self._load_companies()
        code = (message.text or "").strip().upper()
        target = next((n for n, i in self._companies.items() if i.get("invite_code", "").upper() == code), None)
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

        if message.from_user.id not in self._companies[comp_name].get("members", []):
            self._companies[comp_name].setdefault("members", []).append(message.from_user.id)
            self._save_companies()

        self._user_active_company[message.from_user.id] = comp_name
        self._bot.send_message(message.chat.id, f"✅ Joined <b>{comp_name}</b>!")
        self._send_main_dashboard(message.chat.id, message.from_user.id)

    # -------------------------------------------------------------------------
    # Results & AI Summary Presentation Delegates
    # -------------------------------------------------------------------------

    def _send_results_view(self, chat_id: int, comp_name: str) -> None:
        results = self._load_latest_results_from_disk()
        if not results:
            self._bot.send_message(
                chat_id,
                "ℹ️ No screening results found yet.\n"
                "Run the AI Screening pipeline from the CLI application first, then view results here!",
                reply_markup=self._keyboards.back_to_dashboard(),
            )
            return

        msg = self._formatter.format_results_overview(comp_name, results)
        self._bot.send_message(chat_id, msg, reply_markup=self._keyboards.results_menu(len(results)))

    def _send_candidate_pdf(self, chat_id: int, comp_name: str, idx: int) -> None:
        results = self._load_latest_results_from_disk()
        if not results or idx > len(results):
            self._bot.send_message(chat_id, "Candidate not found.")
            return

        filename = results[idx - 1].get("file", "")
        pdf_path = self._company_resumes_folder(comp_name) / filename
        if not pdf_path.exists():
            pdf_path = Path("resumes") / filename

        if pdf_path.exists():
            with open(pdf_path, "rb") as f:
                self._bot.send_document(chat_id, f, caption=f"📄 Resume: <b>{filename}</b>")
        else:
            self._bot.send_message(chat_id, f"❌ Local PDF file '{filename}' not found.")

    def _send_summary_breakdown(self, chat_id: int, comp_name: str) -> None:
        summary_data = self._load_summary_json()
        results = self._load_latest_results_from_disk()
        if not summary_data and not results:
            self._bot.send_message(
                chat_id,
                "ℹ️ No AI Summary Report available yet.\n"
                "Run the AI Screening pipeline on the CLI first to generate the summary report!",
                reply_markup=self._keyboards.back_to_dashboard(),
            )
            return

        rules = self._get_rules()
        msg = self._formatter.format_summary_report(
            comp_name, rules, results, summary_data=summary_data
        )
        self._bot.send_message(chat_id, msg, reply_markup=self._keyboards.back_to_dashboard())

    # -------------------------------------------------------------------------
    # Polling Starter
    # -------------------------------------------------------------------------

    def start(self) -> None:
        """Starts the Telegram bot polling loop."""
        if not self._bot:
            print("[TelegramBot] Error: bot not initialized.")
            return
        print("  [TelegramBot] Cloud Resume Upload Companion Bot started...")
        self._bot.infinity_polling(timeout=20, long_polling_timeout=10)


if __name__ == "__main__":
    telegram_io = TelegramIOManager()
    telegram_io.start()
