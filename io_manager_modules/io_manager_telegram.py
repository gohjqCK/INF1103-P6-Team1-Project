import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from datetime import datetime, timedelta, timezone
import hashlib
import html
import io
import os
import secrets
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from io_manager_modules.io_manager_base import BaseIOManager
from io_manager_modules.telegram_formatter import TelegramFormatter
from io_manager_modules.telegram_keyboards import TelegramKeyboards

try:
    from data_manager_modules.data_manager_side import DataManager
    _DATA_MANAGER_AVAILABLE = True
except Exception:
    DataManager = None
    _DATA_MANAGER_AVAILABLE = False

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

SGT_TIMEZONE = timezone(timedelta(hours=8))


class TelegramIOManager(BaseIOManager):
    """Full Telegram Bot UI implementing BaseIOManager for headless server operation.

    All persistence routes through a cloud-ready DataManager contract with in-memory
    mock/stub storage fallback (no local companies/ folder or companies.json files).
    """

    MIN_RULE_LENGTH = 5
    MAX_RULE_LENGTH = 300

    def __init__(
        self,
        token: Optional[str] = None,
        data_manager: Optional[Any] = None,
        pipeline_runner: Optional[Callable[..., Any]] = None,
        use_cloud: Optional[bool] = None,
    ):
        if "load_dotenv" in globals():
            load_dotenv()

        self._token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        if not self._token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN not found! Please set it in your .env file or environment variables."
            )

        if data_manager is not None:
            self._data_manager = data_manager
        elif _DATA_MANAGER_AVAILABLE:
            try:
                self._data_manager = DataManager()
            except Exception as err:
                self._log_server_event("INIT", f"DataManager init skipped ({err}); using stub storage.")
                self._data_manager = None
        else:
            self._data_manager = None

        self._use_cloud = (
            bool(getattr(self._data_manager, "CLOUD_READY", False))
            if use_cloud is None
            else bool(use_cloud)
        )

        # Helper components (Composition)
        self._keyboards = TelegramKeyboards()
        self._formatter = TelegramFormatter()
        self._pipeline_runner = pipeline_runner

        # Thread-safe in-memory stub stores (used until DataManager cloud methods are active)
        self._lock = threading.RLock()
        self._next_stub_company_id = 101
        self._companies: Dict[str, Dict[str, Any]] = {}
        self._company_rules: Dict[int, List[Dict[str, Any]]] = {}
        self._company_resumes: Dict[int, List[Dict[str, Any]]] = {}
        self._company_results: Dict[int, List[Dict[str, Any]]] = {}
        self._company_summaries: Dict[int, Dict[str, Any]] = {}
        self._company_filtered_resumes: Dict[int, Dict[str, Any]] = {}

        # Per-user / per-chat session tracking
        self._sessions: Dict[int, Dict[str, Any]] = {}
        self._user_active_company: Dict[int, str] = {}
        self._latest_results: List[Dict[str, Any]] = []

        if not _TELEBOT_AVAILABLE:
            self._bot = None
            self._log_server_event("ERROR", "pyTelegramBotAPI not installed. Run 'pip install pyTelegramBotAPI'.")
            return

        self._bot = telebot.TeleBot(self._token, parse_mode="HTML")
        self._register_handlers()

    # -------------------------------------------------------------------------
    # Server Console Logging
    # -------------------------------------------------------------------------

    @staticmethod
    def _log_server_event(category: str, message: str) -> None:
        timestamp = datetime.now(SGT_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S SGT")
        print(f"[{timestamp}] [TELEGRAM:{category}] {message}")

    # -------------------------------------------------------------------------
    # BaseIOManager Contract Implementations
    # -------------------------------------------------------------------------

    def display_message(self, message: str) -> None:
        self._log_server_event("INFO", message)

    def display_error(self, error_message: str) -> None:
        self._log_server_event("ERROR", error_message)

    def display_success(self, success_message: str) -> None:
        self._log_server_event("SUCCESS", success_message)

    def display_screening_results(
        self, ranked_candidates: List[Any], top_n: Optional[int] = None
    ) -> List[Any]:
        self._latest_results = list(ranked_candidates or [])
        top_list = self._latest_results[:top_n] if top_n else self._latest_results
        self._log_server_event("RESULTS", f"Prepared {len(top_list)} ranked candidate(s).")
        return top_list

    def get_employer_inputs(self, rerun_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Returns active company inputs for BaseIOManager compatibility."""
        with self._lock:
            comp_name = next(iter(self._companies), "General")
            comp_info = self._companies.get(comp_name, {})
            comp_id = comp_info.get("company_id", 101)
            rules = self._dm_get_rules(comp_id)
        return {
            "company_name": comp_name,
            "company_id": comp_id,
            "business_rules": rules,
            "top_n": 3,
        }

    # -------------------------------------------------------------------------
    # Cloud-Ready DataManager Bridge (with In-Memory Stub Fallback)
    # -------------------------------------------------------------------------

    def _dm_create_company(
        self,
        name: str,
        passcode_hash: str,
        owner_id: int,
        invite_code: str,
    ) -> Dict[str, Any]:
        """Creates a company via DataManager cloud API if ready, else in-memory stub."""
        if (
            self._use_cloud
            and self._data_manager is not None
            and hasattr(self._data_manager, "create_company")
        ):
            record = self._data_manager.create_company(
                company_name=name,
                passcode_hash=passcode_hash,
                owner_id=owner_id,
                invite_code=invite_code,
            )
            with self._lock:
                self._companies[record["company_name"]] = record
            return record

        with self._lock:
            for existing_name in self._companies:
                if existing_name.lower() == name.lower():
                    raise ValueError(f"Company '{existing_name}' already exists.")

            comp_id = self._next_stub_company_id
            self._next_stub_company_id += 1
            record = {
                "company_id": comp_id,
                "company_name": name,
                "invite_code": invite_code,
                "passcode_hash": passcode_hash,
                "owner": owner_id,
                "members": [owner_id],
            }
            self._companies[name] = record
            self._company_rules.setdefault(comp_id, [])
            self._company_resumes.setdefault(comp_id, [])
            return dict(record)

    def _dm_get_company_by_invite(self, invite_code: str) -> Optional[Dict[str, Any]]:
        """Looks up a company by invite code via DataManager cloud API or stub."""
        code = invite_code.strip().upper()
        if (
            self._use_cloud
            and self._data_manager is not None
            and hasattr(self._data_manager, "get_company_by_invite")
        ):
            record = self._data_manager.get_company_by_invite(code)
            if record:
                with self._lock:
                    self._companies[record["company_name"]] = record
            return record

        with self._lock:
            for record in self._companies.values():
                if str(record.get("invite_code", "")).upper() == code:
                    return dict(record)
        return None

    def _dm_add_company_member(self, company_id: int, comp_name: str, user_id: int) -> None:
        if (
            self._use_cloud
            and self._data_manager is not None
            and hasattr(self._data_manager, "add_company_member")
        ):
            self._data_manager.add_company_member(company_id=company_id, user_id=user_id)

        with self._lock:
            if comp_name in self._companies:
                members = self._companies[comp_name].setdefault("members", [])
                if user_id not in members:
                    members.append(user_id)

    def _dm_get_rules(self, company_id: int) -> List[Dict[str, Any]]:
        if (
            self._use_cloud
            and self._data_manager is not None
            and hasattr(self._data_manager, "get_company_rules")
        ):
            return list(self._data_manager.get_company_rules(company_id) or [])

        with self._lock:
            return [dict(r) for r in self._company_rules.get(company_id, [])]

    def _dm_save_rules(self, company_id: int, rules: List[Dict[str, Any]]) -> None:
        if (
            self._use_cloud
            and self._data_manager is not None
            and hasattr(self._data_manager, "save_company_rules")
        ):
            self._data_manager.save_company_rules(company_id, rules)
            return

        with self._lock:
            self._company_rules[company_id] = [dict(r) for r in rules]

    def _parse_pdf_bytes_in_memory(self, file_name: str, pdf_bytes: bytes) -> Dict[str, Any]:
        """Parses PDF bytes in memory using DataManager.parse_pdf_bytes or pypdf fallback."""
        if self._data_manager is not None and hasattr(self._data_manager, "parse_pdf_bytes"):
            resume_obj = self._data_manager.parse_pdf_bytes(file_name, pdf_bytes)
            result = resume_obj.to_dict()
            result["file_name"] = file_name
            return result

        if not _PYPDF_AVAILABLE:
            return {
                "file": file_name,
                "file_name": file_name,
                "status": "valid",
                "reason": "",
                "pages": 1,
                "text": "",
            }

        try:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            pages = len(reader.pages)
            text = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
            if len(text) < 200:
                return {
                    "file": file_name,
                    "file_name": file_name,
                    "status": "invalid",
                    "reason": "No readable text (it may be a scanned image)",
                    "pages": pages,
                    "text": text,
                }
            if len(text) > 20000:
                return {
                    "file": file_name,
                    "file_name": file_name,
                    "status": "invalid",
                    "reason": f"Too long for one resume ({pages} pages)",
                    "pages": pages,
                    "text": text,
                }
            return {
                "file": file_name,
                "file_name": file_name,
                "status": "valid",
                "reason": "",
                "pages": pages,
                "text": text,
            }
        except Exception as err:
            return {
                "file": file_name,
                "file_name": file_name,
                "status": "invalid",
                "reason": f"Could not read the PDF file: {err}",
                "pages": 0,
                "text": "",
            }

    def _dm_upload_resume(
        self,
        company_id: int,
        company_name: str,
        file_name: str,
        pdf_bytes: bytes,
    ) -> Dict[str, Any]:
        """Parses and stores an uploaded PDF resume via DataManager cloud API or stub."""
        if (
            self._use_cloud
            and self._data_manager is not None
            and hasattr(self._data_manager, "upload_resume_bytes")
        ):
            result = self._data_manager.upload_resume_bytes(
                file_name=file_name,
                pdf_bytes=pdf_bytes,
                company_id=company_id,
            )
            result.setdefault("file_name", file_name)
            result.setdefault("source", "Supabase Cloud")
            return result

        parsed = self._parse_pdf_bytes_in_memory(file_name, pdf_bytes)
        entry = {
            "file": file_name,
            "file_name": file_name,
            "status": parsed.get("status", "valid"),
            "reason": parsed.get("reason", ""),
            "pages": parsed.get("pages", 0),
            "text": parsed.get("text", ""),
            "pdf_bytes": pdf_bytes,
            "company_id": company_id,
            "company_name": company_name,
            "source": "Session Memory (Cloud Stub)",
        }

        with self._lock:
            bucket = self._company_resumes.setdefault(company_id, [])
            bucket = [r for r in bucket if r.get("file_name") != file_name]
            bucket.append(entry)
            self._company_resumes[company_id] = bucket
        return dict(entry)

    def _dm_list_resumes(self, company_id: int) -> List[Dict[str, Any]]:
        if (
            self._use_cloud
            and self._data_manager is not None
            and hasattr(self._data_manager, "list_company_resumes")
        ):
            return list(self._data_manager.list_company_resumes(company_id) or [])

        if (
            self._use_cloud
            and self._data_manager is not None
            and hasattr(self._data_manager, "db_handler")
        ):
            rows = self._data_manager.db_handler.fetch_resume_files(company_id=company_id)
            return [
                {
                    "file": row.get("file_name"),
                    "file_name": row.get("file_name"),
                    "status": row.get("status", "valid"),
                    "reason": row.get("invalid_reason", ""),
                    "pages": row.get("pages", 0),
                    "text": row.get("parsed_text", ""),
                    "pdf_url": row.get("pdf_url", ""),
                    "source": "Supabase Cloud",
                }
                for row in rows
            ]

        with self._lock:
            return [dict(r) for r in self._company_resumes.get(company_id, [])]

    def _dm_delete_resume(self, company_id: int, file_name: str) -> bool:
        if (
            self._use_cloud
            and self._data_manager is not None
            and hasattr(self._data_manager, "delete_company_resume")
        ):
            return bool(self._data_manager.delete_company_resume(company_id, file_name))

        with self._lock:
            bucket = self._company_resumes.get(company_id, [])
            new_bucket = [r for r in bucket if r.get("file_name") != file_name]
            removed = len(new_bucket) < len(bucket)
            self._company_resumes[company_id] = new_bucket
            return removed

    def _dm_clear_resumes(self, company_id: int) -> None:
        if (
            self._use_cloud
            and self._data_manager is not None
            and hasattr(self._data_manager, "clear_company_resumes")
        ):
            self._data_manager.clear_company_resumes(company_id)
            return

        with self._lock:
            self._company_resumes[company_id] = []

    def _dm_get_resume_pdf_bytes(self, company_id: int, file_name: str) -> Optional[bytes]:
        if (
            self._use_cloud
            and self._data_manager is not None
            and hasattr(self._data_manager, "download_resume_bytes")
        ):
            return self._data_manager.download_resume_bytes(company_id, file_name)

        with self._lock:
            for item in self._company_resumes.get(company_id, []):
                if item.get("file_name") == file_name:
                    return item.get("pdf_bytes")
        return None

    def _dm_save_screening_results(
        self,
        company_id: int,
        ranked_candidates: List[Dict[str, Any]],
        summary_data: Optional[Dict[str, Any]],
        filtered_resumes: Optional[Dict[str, Any]] = None,
    ) -> None:
        if (
            self._use_cloud
            and self._data_manager is not None
            and hasattr(self._data_manager, "save_screening_results")
        ):
            self._data_manager.save_screening_results(
                company_id=company_id,
                ranked_candidates=ranked_candidates,
                summary_data=summary_data,
                filtered_resumes=filtered_resumes,
            )

        with self._lock:
            self._company_results[company_id] = list(ranked_candidates)
            if summary_data is not None:
                self._company_summaries[company_id] = dict(summary_data)
            if filtered_resumes is not None:
                self._company_filtered_resumes[company_id] = dict(filtered_resumes)

    def _dm_get_screening_results(
        self, company_id: int
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        if (
            self._use_cloud
            and self._data_manager is not None
            and hasattr(self._data_manager, "get_screening_results")
        ):
            res = self._data_manager.get_screening_results(company_id)
            if isinstance(res, tuple) and len(res) == 2:
                return res[0] or [], res[1]

        with self._lock:
            return (
                list(self._company_results.get(company_id, [])),
                self._company_summaries.get(company_id),
            )

    # -------------------------------------------------------------------------
    # Session & Helper Utilities
    # -------------------------------------------------------------------------

    def _get_session(self, chat_id: int) -> Dict[str, Any]:
        with self._lock:
            if chat_id not in self._sessions:
                self._sessions[chat_id] = {"top_n": 3, "pending_rule_text": None}
            return self._sessions[chat_id]

    def _get_active_company(self, user_id: int) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        with self._lock:
            comp_name = self._user_active_company.get(user_id)
            if comp_name and comp_name in self._companies:
                return comp_name, self._companies[comp_name]
            for name, info in self._companies.items():
                if user_id == info.get("owner") or user_id in info.get("members", []):
                    self._user_active_company[user_id] = name
                    return name, info
        return None, None

    def _send_safe_html(
        self,
        chat_id: int,
        text: str,
        reply_markup: Any = None,
    ) -> None:
        """Sends long HTML messages safely within Telegram's 4096-char limit."""
        if len(text) <= 4000:
            self._bot.send_message(chat_id, text, reply_markup=reply_markup)
            return

        chunks: List[str] = []
        current = ""
        for line in text.splitlines(keepends=True):
            if len(current) + len(line) > 3900:
                chunks.append(current)
                current = line
            else:
                current += line
        if current:
            chunks.append(current)

        for idx, chunk in enumerate(chunks):
            markup = reply_markup if idx == len(chunks) - 1 else None
            self._bot.send_message(chat_id, chunk, reply_markup=markup)

    def _edit_safe_html(self, chat_id: int, message_id: int, text: str) -> None:
        try:
            self._bot.edit_message_text(text, chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # UI Presentations
    # -------------------------------------------------------------------------

    def _send_main_dashboard(self, chat_id: int, user_id: int) -> None:
        comp_name, comp_info = self._get_active_company(user_id)
        if not comp_name or not comp_info:
            self._bot.send_message(
                chat_id,
                "<b>Welcome to RESUM-AI!</b>\n\n"
                "Create a new Company Folder or join your team's folder to get started:",
                reply_markup=self._keyboards.auth_menu(),
            )
            return

        comp_id = comp_info["company_id"]
        rules = self._dm_get_rules(comp_id)
        resumes = self._dm_list_resumes(comp_id)
        results, _ = self._dm_get_screening_results(comp_id)
        session = self._get_session(chat_id)
        top_n = session.get("top_n", 3)

        msg = self._formatter.format_dashboard(
            company_name=comp_name,
            invite_code=comp_info.get("invite_code", "N/A"),
            company_id=comp_id,
            resume_count=len(resumes),
            rule_count=len(rules),
            top_n=top_n,
            has_results=bool(results),
        )
        self._bot.send_message(
            chat_id,
            msg,
            reply_markup=self._keyboards.dashboard_menu(
                rule_count=len(rules),
                resume_count=len(resumes),
                top_n=top_n,
            ),
        )

    def _send_rules_menu(self, chat_id: int, comp_name: str, comp_id: int) -> None:
        rules = self._dm_get_rules(comp_id)
        msg = self._formatter.format_rules_list(comp_name, rules)
        self._send_safe_html(chat_id, msg, reply_markup=self._keyboards.rules_menu(has_rules=bool(rules)))

    def _send_resumes_menu(self, chat_id: int, comp_name: str, comp_id: int) -> None:
        resumes = self._dm_list_resumes(comp_id)
        msg = self._formatter.format_resumes_list(comp_name, resumes)
        self._send_safe_html(
            chat_id,
            msg,
            reply_markup=self._keyboards.resumes_menu(has_resumes=bool(resumes)),
        )

    # -------------------------------------------------------------------------
    # Telegram Handler Registration
    # -------------------------------------------------------------------------

    def _register_handlers(self) -> None:
        @self._bot.message_handler(commands=["start", "menu", "help"])
        def handle_start(message: Message):
            user_label = message.from_user.username or message.from_user.first_name or str(message.from_user.id)
            self._log_server_event("COMMAND", f"/{message.text.lstrip('/').split()[0]} from user={user_label} (id={message.from_user.id})")
            self._send_main_dashboard(message.chat.id, message.from_user.id)

        @self._bot.message_handler(content_types=["document"])
        def handle_pdf_upload(message: Message):
            comp_name, comp_info = self._get_active_company(message.from_user.id)
            if not comp_name or not comp_info:
                self._bot.reply_to(message, "⚠️ Create or join a Company Folder first using /start.")
                return

            doc = message.document
            if not doc.file_name or not doc.file_name.lower().endswith(".pdf"):
                self._bot.reply_to(message, "❌ Only <b>.pdf</b> files are accepted.")
                return

            comp_id = comp_info["company_id"]
            safe_fname = html.escape(doc.file_name)
            safe_cname = html.escape(comp_name)
            status_msg = self._bot.reply_to(
                message,
                f"⏳ Processing <b>{safe_fname}</b> for <b>{safe_cname}</b>...",
            )
            try:
                file_info = self._bot.get_file(doc.file_id)
                pdf_bytes = self._bot.download_file(file_info.file_path)

                upload_info = self._dm_upload_resume(
                    company_id=comp_id,
                    company_name=comp_name,
                    file_name=doc.file_name,
                    pdf_bytes=pdf_bytes,
                )

                status = upload_info.get("status", "valid")
                pages = upload_info.get("pages", 0)
                reason = html.escape(str(upload_info.get("reason", "")))
                total_resumes = len(self._dm_list_resumes(comp_id))

                self._log_server_event(
                    "UPLOAD",
                    f"company='{comp_name}' (#{comp_id}) file='{doc.file_name}' status={status} pages={pages}",
                )

                if status == "valid":
                    self._bot.edit_message_text(
                        f"✅ <b>{safe_fname}</b> uploaded!\n"
                        f"🏢 Company: <b>{safe_cname}</b> <code>(ID: #{comp_id})</code>\n"
                        f"📄 Pages: <b>{pages}</b> | Status: <b>VALID</b>\n"
                        f"📁 Total Resumes in Folder: <b>{total_resumes}</b>",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                        reply_markup=self._keyboards.back_to_dashboard(),
                    )
                else:
                    self._bot.edit_message_text(
                        f"⚠️ <b>{safe_fname}</b> saved but marked <b>INVALID</b>:\n"
                        f"<i>{reason}</i>\n"
                        f"📁 Total Resumes in Folder: <b>{total_resumes}</b>",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                        reply_markup=self._keyboards.back_to_dashboard(),
                    )
            except Exception as err:
                self._log_server_event("ERROR", f"PDF upload failed for '{doc.file_name}': {err}")
                self._bot.edit_message_text(
                    f"❌ Upload failed: {html.escape(str(err))}",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                )

        @self._bot.message_handler(content_types=["text"])
        def handle_text_message(message: Message):
            self._bot.reply_to(
                message,
                "📤 Send a <b>.pdf</b> resume here to upload it, or tap /menu to open your dashboard.",
            )

        @self._bot.callback_query_handler(func=lambda call: True)
        def handle_callbacks(call: CallbackQuery):
            chat_id = call.message.chat.id
            user_id = call.from_user.id
            data = call.data or ""
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
                with self._lock:
                    self._user_active_company.pop(user_id, None)
                self._log_server_event("AUTH", f"User {user_id} opened Switch/Logout menu.")
                self._bot.send_message(
                    chat_id,
                    "🔄 <b>Switch or Authenticate Company Folder:</b>",
                    reply_markup=self._keyboards.auth_menu(),
                )
                return

            comp_name, comp_info = self._get_active_company(user_id)
            if not comp_name or not comp_info:
                self._bot.send_message(
                    chat_id,
                    "Please create or join a company folder first:",
                    reply_markup=self._keyboards.auth_menu(),
                )
                return

            comp_id = comp_info["company_id"]

            if data == "menu_main":
                self._send_main_dashboard(chat_id, user_id)

            # ---- Business Rules CRUD ----
            elif data == "menu_rules":
                self._send_rules_menu(chat_id, comp_name, comp_id)

            elif data == "rule_add":
                msg = self._bot.send_message(
                    chat_id,
                    f"✏️ Enter the new rule requirement ({self.MIN_RULE_LENGTH}-{self.MAX_RULE_LENGTH} characters):",
                )
                self._bot.register_next_step_handler(msg, self._step_add_rule_text, comp_name, comp_id)

            elif data.startswith("rule_prio:"):
                prio = data.split(":", 1)[1]
                session = self._get_session(chat_id)
                rule_text = session.get("pending_rule_text")
                if rule_text:
                    rules = self._dm_get_rules(comp_id)
                    if any(r.get("text", "").lower() == rule_text.lower() for r in rules):
                        self._bot.send_message(chat_id, f"⚠️ Rule <i>\"{html.escape(rule_text)}\"</i> already exists.")
                    else:
                        rules.append({"text": rule_text, "priority": prio})
                        self._dm_save_rules(comp_id, rules)
                        self._log_server_event("RULES", f"company='{comp_name}' added [{prio}] '{rule_text}'")
                        self._bot.send_message(
                            chat_id,
                            f"✅ Added Rule: <b>[{html.escape(prio.upper())}]</b> {html.escape(rule_text)}",
                        )
                    session["pending_rule_text"] = None
                self._send_rules_menu(chat_id, comp_name, comp_id)

            elif data == "rule_del_menu":
                rules = self._dm_get_rules(comp_id)
                if not rules:
                    self._bot.send_message(chat_id, "ℹ️ No rules available to delete.")
                    return
                self._bot.send_message(
                    chat_id,
                    "Tap a rule below to delete it:",
                    reply_markup=self._keyboards.delete_rules_menu(rules),
                )

            elif data.startswith("rule_del:"):
                idx = int(data.split(":", 1)[1])
                rules = self._dm_get_rules(comp_id)
                if 1 <= idx <= len(rules):
                    removed = rules.pop(idx - 1)
                    self._dm_save_rules(comp_id, rules)
                    self._log_server_event("RULES", f"company='{comp_name}' deleted '{removed.get('text', '')}'")
                    self._bot.send_message(
                        chat_id,
                        f"🗑 Removed Rule: <b>{html.escape(str(removed.get('text', '')))}</b>",
                    )
                self._send_rules_menu(chat_id, comp_name, comp_id)

            elif data == "rule_clear":
                self._dm_save_rules(comp_id, [])
                self._log_server_event("RULES", f"company='{comp_name}' cleared all rules.")
                self._bot.send_message(chat_id, "🧹 All business rules cleared.")
                self._send_rules_menu(chat_id, comp_name, comp_id)

            # ---- Resume Management ----
            elif data == "menu_resumes":
                self._send_resumes_menu(chat_id, comp_name, comp_id)

            elif data == "res_del_menu":
                resumes = self._dm_list_resumes(comp_id)
                if not resumes:
                    self._bot.send_message(chat_id, "ℹ️ No resumes available to delete.")
                    return
                self._bot.send_message(
                    chat_id,
                    "Tap a resume below to delete it:",
                    reply_markup=self._keyboards.delete_resumes_menu(resumes),
                )

            elif data.startswith("res_del:"):
                idx = int(data.split(":", 1)[1])
                resumes = self._dm_list_resumes(comp_id)
                if 1 <= idx <= len(resumes):
                    target_name = resumes[idx - 1].get("file_name") or resumes[idx - 1].get("file")
                    if target_name and self._dm_delete_resume(comp_id, target_name):
                        self._log_server_event("RESUMES", f"company='{comp_name}' deleted '{target_name}'")
                        self._bot.send_message(chat_id, f"🗑 Removed Resume: <b>{html.escape(target_name)}</b>")
                self._send_resumes_menu(chat_id, comp_name, comp_id)

            elif data == "res_clear":
                self._dm_clear_resumes(comp_id)
                self._log_server_event("RESUMES", f"company='{comp_name}' cleared all resumes.")
                self._bot.send_message(chat_id, "🧹 All resumes cleared for this company.")
                self._send_resumes_menu(chat_id, comp_name, comp_id)

            # ---- Top-N Limit Configuration ----
            elif data == "menu_topn":
                curr_n = self._get_session(chat_id).get("top_n", 3)
                self._bot.send_message(
                    chat_id,
                    f"🎯 <b>Select Candidate Shortlist Limit (Top N):</b>\n\n"
                    f"Current limit: <b>{curr_n}</b>",
                    reply_markup=self._keyboards.top_n_menu(curr_n),
                )

            elif data == "set_topn_custom":
                msg = self._bot.send_message(
                    chat_id,
                    "✏️ <b>Enter Custom Top N Limit:</b>\n"
                    "Send a positive whole number between <code>1</code> and <code>100</code>:",
                )
                self._bot.register_next_step_handler(msg, self._step_set_custom_topn)

            elif data.startswith("set_topn:"):
                val = int(data.split(":", 1)[1])
                self._get_session(chat_id)["top_n"] = val
                self._log_server_event("CONFIG", f"company='{comp_name}' set top_n={val}")
                self._bot.send_message(chat_id, f"🎯 <b>Top N Shortlist Limit set to {val}!</b>")
                self._send_main_dashboard(chat_id, user_id)

            # ---- Screening, Results & Summary ----
            elif data == "menu_screen":
                self._trigger_screening(chat_id, user_id, comp_name, comp_id)

            elif data == "menu_results":
                self._send_results_view(chat_id, comp_name, comp_id)

            elif data == "menu_summary":
                self._send_summary_breakdown(chat_id, comp_name, comp_id)

            elif data.startswith("cand_view:"):
                idx = int(data.split(":", 1)[1])
                results, _ = self._dm_get_screening_results(comp_id)
                top_n = self._get_session(chat_id).get("top_n", 3)
                ranked = results[:top_n]
                if 1 <= idx <= len(ranked):
                    msg = self._formatter.format_candidate_profile(ranked[idx - 1], idx)
                    self._send_safe_html(chat_id, msg, reply_markup=self._keyboards.candidate_profile_menu(idx))
                else:
                    self._bot.send_message(chat_id, "⚠️ Candidate profile not found. Re-open results.")

            elif data.startswith("cand_pdf:"):
                idx = int(data.split(":", 1)[1])
                self._send_candidate_pdf(chat_id, comp_name, comp_id, idx)

    # -------------------------------------------------------------------------
    # Conversational Step Handlers
    # -------------------------------------------------------------------------

    def _step_set_custom_topn(self, message: Message) -> None:
        text = (message.text or "").strip()
        if not text.isdigit() or int(text) < 1:
            msg = self._bot.reply_to(
                message,
                "❌ <b>Invalid input!</b> Please send a positive number greater than 0 (e.g. 2, 5, 10):",
            )
            self._bot.register_next_step_handler(msg, self._step_set_custom_topn)
            return

        val = min(int(text), 100)
        self._get_session(message.chat.id)["top_n"] = val
        self._log_server_event("CONFIG", f"user={message.from_user.id} set custom top_n={val}")
        self._bot.send_message(message.chat.id, f"✅ <b>Top N Shortlist Limit set to {val}!</b>")
        self._send_main_dashboard(message.chat.id, message.from_user.id)

    def _step_create_company_name(self, message: Message) -> None:
        name = (message.text or "").strip()
        if len(name) < 2:
            self._bot.reply_to(message, "❌ Company name must be at least 2 characters. Use /start to try again.")
            return
        msg = self._bot.reply_to(
            message,
            f"🔒 Set a <b>Passcode</b> for <b>{html.escape(name)}</b> (min 4 characters):",
        )
        self._bot.register_next_step_handler(msg, self._step_create_company_passcode, name)

    def _step_create_company_passcode(self, message: Message, name: str) -> None:
        passcode = (message.text or "").strip()
        if len(passcode) < 4:
            self._bot.reply_to(message, "❌ Passcode must be at least 4 characters. Use /start to try again.")
            return

        prefix = "".join(c for c in name.upper() if c.isalnum())[:4] or "COMP"
        invite_code = f"{prefix}-{secrets.randbelow(9000) + 1000}"
        passcode_hash = hashlib.sha256(passcode.encode("utf-8")).hexdigest()

        try:
            record = self._dm_create_company(
                name=name,
                passcode_hash=passcode_hash,
                owner_id=message.from_user.id,
                invite_code=invite_code,
            )
        except Exception as err:
            self._bot.reply_to(message, f"❌ Could not create company: {html.escape(str(err))}")
            return

        comp_id = record["company_id"]
        with self._lock:
            self._user_active_company[message.from_user.id] = record["company_name"]

        self._log_server_event(
            "AUTH",
            f"Created company '{record['company_name']}' (id=#{comp_id}, invite={invite_code}) by user={message.from_user.id}",
        )
        self._bot.send_message(
            message.chat.id,
            f"🎉 <b>Company Created!</b>\n"
            f"🏢 <b>{html.escape(record['company_name'])}</b> <code>(ID: #{comp_id})</code>\n"
            f"🔑 Invite Code: <code>{html.escape(invite_code)}</code>\n\n"
            f"<i>Share this Invite Code and Passcode with your team so they can join!</i>",
        )
        self._send_main_dashboard(message.chat.id, message.from_user.id)

    def _step_join_company_code(self, message: Message) -> None:
        code = (message.text or "").strip().upper()
        record = self._dm_get_company_by_invite(code)
        if not record:
            self._bot.reply_to(message, "❌ Invalid Invite Code. Use /start to try again.")
            return
        msg = self._bot.reply_to(
            message,
            f"🔒 Enter Passcode for <b>{html.escape(record['company_name'])}</b>:",
        )
        self._bot.register_next_step_handler(msg, self._step_join_company_passcode, record)

    def _step_join_company_passcode(self, message: Message, record: Dict[str, Any]) -> None:
        passcode = (message.text or "").strip()
        target_hash = record.get("passcode_hash")
        if hashlib.sha256(passcode.encode("utf-8")).hexdigest() != target_hash:
            self._bot.reply_to(message, "❌ Incorrect Passcode. Use /start to try again.")
            return

        comp_name = record["company_name"]
        comp_id = record["company_id"]
        self._dm_add_company_member(comp_id, comp_name, message.from_user.id)
        with self._lock:
            self._user_active_company[message.from_user.id] = comp_name

        self._log_server_event("AUTH", f"User {message.from_user.id} joined '{comp_name}' (id=#{comp_id}).")
        self._bot.send_message(message.chat.id, f"✅ Joined <b>{html.escape(comp_name)}</b>!")
        self._send_main_dashboard(message.chat.id, message.from_user.id)

    def _step_add_rule_text(self, message: Message, comp_name: str, comp_id: int) -> None:
        text = (message.text or "").strip()
        if len(text) < self.MIN_RULE_LENGTH or len(text) > self.MAX_RULE_LENGTH:
            self._bot.reply_to(
                message,
                f"❌ Rule must be {self.MIN_RULE_LENGTH}-{self.MAX_RULE_LENGTH} characters. Tap Manage Business Rules to try again.",
            )
            self._send_rules_menu(message.chat.id, comp_name, comp_id)
            return

        existing = self._dm_get_rules(comp_id)
        if any(r.get("text", "").lower() == text.lower() for r in existing):
            self._bot.reply_to(message, "❌ That rule is already configured. Please enter a unique rule.")
            self._send_rules_menu(message.chat.id, comp_name, comp_id)
            return

        self._get_session(message.chat.id)["pending_rule_text"] = text
        self._bot.send_message(
            message.chat.id,
            f"Select priority weight for:\n<i>\"{html.escape(text)}\"</i>",
            reply_markup=self._keyboards.priority_selection_menu(),
        )

    # -------------------------------------------------------------------------
    # Pipeline & Presentation Delegates
    # -------------------------------------------------------------------------

    def _trigger_screening(self, chat_id: int, user_id: int, comp_name: str, comp_id: int) -> None:
        rules = self._dm_get_rules(comp_id)
        if not rules:
            self._bot.send_message(
                chat_id,
                "⚠️ Please configure at least one Business Rule before running screening!",
                reply_markup=self._keyboards.rules_menu(has_rules=False),
            )
            return

        resumes = self._dm_list_resumes(comp_id)
        if not resumes:
            self._bot.send_message(
                chat_id,
                "⚠️ No resumes uploaded yet! Send one or more <b>.pdf</b> files in this chat first.",
                reply_markup=self._keyboards.back_to_dashboard(),
            )
            return

        session = self._get_session(chat_id)
        top_n = min(session.get("top_n", 3), len(resumes))

        employer_inputs = {
            "company_name": comp_name,
            "company_id": comp_id,
            "business_rules": rules,
            "resumes": [
                {
                    "file": r.get("file") or r.get("file_name"),
                    "status": r.get("status", "valid"),
                    "reason": r.get("reason", ""),
                    "pages": r.get("pages", 0),
                    "text": r.get("text", ""),
                }
                for r in resumes
            ],
            "top_n": top_n,
            "output_directory": "output",
        }

        if not (self._pipeline_runner and callable(self._pipeline_runner)):
            self._bot.send_message(
                chat_id,
                "⚠️ Screening pipeline runner is not attached (standalone mode).",
                reply_markup=self._keyboards.back_to_dashboard(),
            )
            return

        wait_msg = self._bot.send_message(
            chat_id,
            f"🚀 <b>Starting AI Screening for {html.escape(comp_name)}...</b>\n"
            f"• Rules: {len(rules)} | Resumes: {len(resumes)} | Top N: {top_n}",
        )
        self._log_server_event(
            "PIPELINE",
            f"Screening triggered by user={user_id} for '{comp_name}' (#{comp_id}) "
            f"[rules={len(rules)}, resumes={len(resumes)}, top_n={top_n}]",
        )

        def on_progress(stage_text: str) -> None:
            self._edit_safe_html(
                chat_id,
                wait_msg.message_id,
                f"⏳ <b>Screening {html.escape(comp_name)}...</b>\n\n{html.escape(stage_text)}",
            )

        try:
            pipeline_output = self._pipeline_runner(employer_inputs, progress_callback=on_progress)
            if isinstance(pipeline_output, dict):
                ranked_candidates = pipeline_output.get("ranked_candidates", [])
                summary_data = pipeline_output.get("summary_data")
                filtered_resumes = pipeline_output.get("filtered_resumes")
            else:
                ranked_candidates = list(pipeline_output or [])
                summary_data = None
                filtered_resumes = None

            self._dm_save_screening_results(
                comp_id,
                ranked_candidates,
                summary_data,
                filtered_resumes=filtered_resumes,
            )
            self.display_screening_results(ranked_candidates, top_n=top_n)

            self._edit_safe_html(
                chat_id,
                wait_msg.message_id,
                f"✅ <b>AI Screening Complete for {html.escape(comp_name)}!</b>\n"
                f"Qualified & ranked candidates: <b>{len(ranked_candidates)}</b>",
            )
            self._send_results_view(chat_id, comp_name, comp_id)
        except Exception as err:
            self._log_server_event("ERROR", f"Screening failed for '{comp_name}': {err}")
            self._edit_safe_html(
                chat_id,
                wait_msg.message_id,
                f"❌ Screening failed: {html.escape(str(err))}",
            )

    def _send_results_view(self, chat_id: int, comp_name: str, comp_id: int) -> None:
        results, _ = self._dm_get_screening_results(comp_id)
        if not results:
            self._bot.send_message(
                chat_id,
                "ℹ️ No screening results yet.\nTap <b>🚀 Run AI Resume Screening</b> on the dashboard first!",
                reply_markup=self._keyboards.back_to_dashboard(),
            )
            return

        session = self._get_session(chat_id)
        ranked = results[: session.get("top_n", 3)]
        msg = self._formatter.format_results_overview(comp_name, ranked)
        self._send_safe_html(chat_id, msg, reply_markup=self._keyboards.results_menu(len(ranked)))

    def _send_candidate_pdf(self, chat_id: int, comp_name: str, comp_id: int, idx: int) -> None:
        results, _ = self._dm_get_screening_results(comp_id)
        top_n = self._get_session(chat_id).get("top_n", 3)
        ranked = results[:top_n]

        if not ranked or idx < 1 or idx > len(ranked):
            self._bot.send_message(chat_id, "⚠️ Candidate not found.")
            return

        filename = ranked[idx - 1].get("file", "")
        if not filename:
            self._bot.send_message(chat_id, "❌ Resume filename not available.")
            return

        pdf_bytes = self._dm_get_resume_pdf_bytes(comp_id, filename)
        if pdf_bytes:
            bio = io.BytesIO(pdf_bytes)
            bio.name = filename
            self._bot.send_document(
                chat_id,
                bio,
                visible_file_name=filename,
                caption=f"📄 Resume ({html.escape(comp_name)}): <b>{html.escape(filename)}</b>",
            )
            return

        # Fallback: check if cloud metadata includes a pdf_url
        resumes = self._dm_list_resumes(comp_id)
        matched = next((r for r in resumes if (r.get("file_name") or r.get("file")) == filename), None)
        if matched and matched.get("pdf_url"):
            self._bot.send_message(
                chat_id,
                f"📄 <b>{html.escape(filename)}</b>\n🔗 Download URL: {html.escape(matched['pdf_url'])}",
            )
            return

        self._bot.send_message(chat_id, f"❌ PDF file '{html.escape(filename)}' not found in storage.")

    def _send_summary_breakdown(self, chat_id: int, comp_name: str, comp_id: int) -> None:
        results, summary_data = self._dm_get_screening_results(comp_id)
        if not results and not summary_data:
            self._bot.send_message(
                chat_id,
                "ℹ️ No summary report yet. Run AI Screening first!",
                reply_markup=self._keyboards.back_to_dashboard(),
            )
            return

        rules = self._dm_get_rules(comp_id)
        msg = self._formatter.format_summary_report(
            comp_name,
            rules,
            results,
            summary_data=summary_data,
        )
        self._send_safe_html(chat_id, msg, reply_markup=self._keyboards.back_to_dashboard())

    # -------------------------------------------------------------------------
    # Polling Starter
    # -------------------------------------------------------------------------

    def start(self) -> None:
        """Starts the Telegram bot polling loop in server mode."""
        if not self._bot:
            self._log_server_event("ERROR", "Bot not initialized.")
            return
        mode = "CLOUD (DataManager)" if self._use_cloud else "CLOUD STUB (In-Memory)"
        self._log_server_event("SERVER", f"Telegram Bot polling started [{mode}]. Waiting for user messages...")
        self._bot.infinity_polling(timeout=20, long_polling_timeout=10)


if __name__ == "__main__":
    telegram_io = TelegramIOManager()
    telegram_io.start()
