"""Telegram Bot UI controller implementing BaseIOManager via modular OOP composition."""
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from datetime import datetime, timedelta, timezone
import html
import io
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from io_manager_modules.io_manager_base import BaseIOManager
from io_manager_modules.telegram_data_bridge import TelegramDataBridge
from io_manager_modules.telegram_formatter import TelegramFormatter
from io_manager_modules.telegram_keyboards import TelegramKeyboards
from io_manager_modules.telegram_session_store import TelegramSessionStore
from io_manager_modules.telegram_validator import PRIORITY_WEIGHTS, TelegramValidator

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
    telebot = None
    CallbackQuery = Any
    Message = Any
    _TELEBOT_AVAILABLE = False

SGT_TIMEZONE = timezone(timedelta(hours=8))


class TelegramIOManager(BaseIOManager):
    """Telegram Bot UI controller implementing BaseIOManager for headless server operation.

    Composes TelegramValidator, TelegramSessionStore, TelegramDataBridge,
    TelegramFormatter, and TelegramKeyboards to separate validation, session state,
    cloud/stub persistence, presentation formatting, and bot routing.
    """

    MIN_RULE_LENGTH = TelegramValidator.MIN_RULE_LENGTH
    MAX_RULE_LENGTH = TelegramValidator.MAX_RULE_LENGTH
    MIN_SET_NAME_LENGTH = TelegramValidator.MIN_SET_NAME_LENGTH
    MAX_SET_NAME_LENGTH = TelegramValidator.MAX_SET_NAME_LENGTH
    PRIORITY_WEIGHTS = dict(PRIORITY_WEIGHTS)

    def __init__(
        self,
        token: Optional[str] = None,
        data_manager: Optional[Any] = None,
        pipeline_runner: Optional[Callable[..., Any]] = None,
        use_cloud: Optional[bool] = None,
        validator: Optional[TelegramValidator] = None,
        session_store: Optional[TelegramSessionStore] = None,
        data_bridge: Optional[TelegramDataBridge] = None,
        formatter: Optional[TelegramFormatter] = None,
        keyboards: Optional[TelegramKeyboards] = None,
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

        # Composed collaborators (Dependency Injection + Encapsulation)
        self._validator = validator or TelegramValidator()
        self._session_store = session_store or TelegramSessionStore()
        self._bridge = data_bridge or TelegramDataBridge(
            data_manager=self._data_manager,
            use_cloud=self._use_cloud,
            validator=self._validator,
        )
        self._formatter = formatter or TelegramFormatter()
        self._keyboards = keyboards or TelegramKeyboards()
        self._pipeline_runner = pipeline_runner
        self._latest_results: List[Dict[str, Any]] = []

        if not _TELEBOT_AVAILABLE:
            self._bot = None
            self._log_server_event("ERROR", "pyTelegramBotAPI not installed. Run 'pip install pyTelegramBotAPI'.")
            return

        self._bot = telebot.TeleBot(self._token, parse_mode="HTML")
        self._register_handlers()

    # -------------------------------------------------------------------------
    # Server Console Logging & Validation Delegates
    # -------------------------------------------------------------------------

    @staticmethod
    def _log_server_event(category: str, message: str) -> None:
        timestamp = datetime.now(SGT_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S SGT")
        print(f"[{timestamp}] [TELEGRAM:{category}] {message}")

    @staticmethod
    def _cap_top_n(requested_n: int, resume_count: int) -> Tuple[int, bool]:
        """Delegates Top-N capping to TelegramValidator."""
        return TelegramValidator.cap_top_n(requested_n, resume_count)

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
        """Returns active company and active rule set inputs for BaseIOManager compatibility."""
        comp_name, comp_id, active_set, rules = self._bridge.get_default_company_inputs()
        return {
            "company_name": comp_name,
            "company_id": comp_id,
            "business_rules_id": active_set.get("rule_set_id") if active_set else None,
            "rule_set_name": active_set.get("set_name") if active_set else None,
            "business_rules": rules,
            "top_n": 3,
        }

    # -------------------------------------------------------------------------
    # Session & Helper Utilities
    # -------------------------------------------------------------------------

    def _get_active_company(self, user_id: int) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        active_name = self._session_store.get_active_company_name(user_id)
        comp_name, comp_info = self._bridge.resolve_user_company(user_id, active_name=active_name)
        if comp_name and comp_name != active_name:
            self._session_store.set_active_company_name(user_id, comp_name)
        return comp_name, comp_info

    def _send_safe_html(
        self,
        chat_id: int,
        text: str,
        reply_markup: Any = None,
    ) -> None:
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
        active_set = self._bridge.get_active_rule_set(comp_id)
        active_set_id = active_set["rule_set_id"] if active_set else None
        active_set_name = active_set["set_name"] if active_set else None
        rules = active_set.get("rules", []) if active_set else []

        resumes = self._bridge.list_resumes(comp_id)
        results, _ = self._bridge.get_screening_results(comp_id, business_rules_id=active_set_id)
        top_n = self._session_store.get_effective_top_n(chat_id, len(resumes))

        msg = self._formatter.format_dashboard(
            company_name=comp_name,
            invite_code=comp_info.get("invite_code", "N/A"),
            company_id=comp_id,
            resume_count=len(resumes),
            rule_count=len(rules),
            top_n=top_n,
            has_results=bool(results),
            active_set_name=active_set_name,
        )
        self._bot.send_message(
            chat_id,
            msg,
            reply_markup=self._keyboards.dashboard_menu(
                rule_count=len(rules),
                resume_count=len(resumes),
                top_n=top_n,
                active_set_name=active_set_name,
            ),
        )

    def _send_rules_menu(self, chat_id: int, comp_name: str, comp_id: int) -> None:
        all_sets = self._bridge.list_rule_sets(comp_id)
        active_set = self._bridge.get_active_rule_set(comp_id)
        rules = active_set.get("rules", []) if active_set else []
        msg = self._formatter.format_rules_list(comp_name, active_set, all_sets)
        self._send_safe_html(
            chat_id,
            msg,
            reply_markup=self._keyboards.rules_menu(
                has_active_set=active_set is not None,
                has_rules=bool(rules),
                set_count=len(all_sets),
            ),
        )

    def _send_resumes_menu(self, chat_id: int, comp_name: str, comp_id: int) -> None:
        resumes = self._bridge.list_resumes(comp_id)
        msg = self._formatter.format_resumes_list(comp_name, resumes)
        self._send_safe_html(
            chat_id,
            msg,
            reply_markup=self._keyboards.resumes_menu(has_resumes=bool(resumes)),
        )

    # -------------------------------------------------------------------------
    # Callback Sub-Routers (Rules, Resumes, Top-N)
    # -------------------------------------------------------------------------

    def _handle_rules_callbacks(
        self, data: str, chat_id: int, comp_name: str, comp_id: int
    ) -> bool:
        """Handles rule-set and rule CRUD callbacks. Returns True if handled."""
        if data == "menu_rules":
            self._send_rules_menu(chat_id, comp_name, comp_id)
            return True

        if data == "ruleset_create":
            msg = self._bot.send_message(
                chat_id,
                "🆕 <b>Create New Business Rule Set</b>\n\n"
                "Enter a name for this role/set (e.g. <code>Finance</code>, <code>Cleaners</code>):",
            )
            self._bot.register_next_step_handler(msg, self._step_create_ruleset_name, comp_name, comp_id)
            return True

        if data == "ruleset_select_menu":
            all_sets = self._bridge.list_rule_sets(comp_id)
            if not all_sets:
                self._bot.send_message(chat_id, "ℹ️ No rule sets exist yet. Create one first!")
                self._send_rules_menu(chat_id, comp_name, comp_id)
                return True
            active_set = self._bridge.get_active_rule_set(comp_id)
            active_id = active_set["rule_set_id"] if active_set else None
            self._bot.send_message(
                chat_id,
                "🔀 <b>Select a Rule Set to activate:</b>",
                reply_markup=self._keyboards.rule_sets_selection_menu(all_sets, active_id),
            )
            return True

        if data.startswith("ruleset_pick:"):
            set_id = int(data.split(":", 1)[1])
            picked = self._bridge.set_active_rule_set(comp_id, set_id)
            if picked:
                self._log_server_event(
                    "RULES",
                    f"company='{comp_name}' swapped active rule set -> '{picked['set_name']}' (#{set_id})",
                )
                self._bot.send_message(
                    chat_id,
                    f"🔀 Switched active Rule Set to <b>{html.escape(picked['set_name'])}</b>!",
                )
            else:
                self._bot.send_message(chat_id, "⚠️ Rule Set not found.")
            self._send_rules_menu(chat_id, comp_name, comp_id)
            return True

        if data == "ruleset_rename":
            active_set = self._bridge.get_active_rule_set(comp_id)
            if not active_set:
                self._bot.send_message(chat_id, "⚠️ No active Rule Set to rename.")
                self._send_rules_menu(chat_id, comp_name, comp_id)
                return True
            msg = self._bot.send_message(
                chat_id,
                f"✏️ Enter a new name for Rule Set <b>{html.escape(active_set['set_name'])}</b>:",
            )
            self._bot.register_next_step_handler(
                msg, self._step_rename_ruleset, comp_name, comp_id, active_set["rule_set_id"]
            )
            return True

        if data == "ruleset_delete":
            active_set = self._bridge.get_active_rule_set(comp_id)
            if not active_set:
                self._bot.send_message(chat_id, "⚠️ No active Rule Set to delete.")
                self._send_rules_menu(chat_id, comp_name, comp_id)
                return True
            deleted_name = active_set["set_name"]
            if self._bridge.delete_rule_set(comp_id, active_set["rule_set_id"]):
                self._log_server_event(
                    "RULES",
                    f"company='{comp_name}' deleted rule set '{deleted_name}' (#{active_set['rule_set_id']})",
                )
                self._bot.send_message(chat_id, f"🗑 Deleted Rule Set <b>{html.escape(deleted_name)}</b>.")
            self._send_rules_menu(chat_id, comp_name, comp_id)
            return True

        if data == "rule_add":
            active_set = self._bridge.get_active_rule_set(comp_id)
            if not active_set:
                self._bot.send_message(chat_id, "⚠️ Create a Rule Set first before adding rules.")
                self._send_rules_menu(chat_id, comp_name, comp_id)
                return True
            msg = self._bot.send_message(
                chat_id,
                f"✏️ Enter a new rule for <b>{html.escape(active_set['set_name'])}</b> "
                f"({self.MIN_RULE_LENGTH}-{self.MAX_RULE_LENGTH} characters):",
            )
            self._bot.register_next_step_handler(
                msg, self._step_add_rule_text, comp_name, comp_id, active_set["rule_set_id"]
            )
            return True

        if data.startswith("rule_prio:"):
            prio = data.split(":", 1)[1]
            rule_text = self._session_store.get_pending_rule_text(chat_id)
            active_set = self._bridge.get_active_rule_set(comp_id)
            if rule_text and active_set:
                rules = list(active_set.get("rules") or [])
                if any(r.get("text", "").lower() == rule_text.lower() for r in rules):
                    self._bot.send_message(
                        chat_id,
                        f"⚠️ Rule <i>\"{html.escape(rule_text)}\"</i> already exists in this set.",
                    )
                else:
                    try:
                        validated = self._validator.validate_and_normalize_rule(rule_text, prio)
                        rules.append(validated)
                        self._bridge.update_rule_set(comp_id, active_set["rule_set_id"], rules=rules)
                        self._log_server_event(
                            "RULES",
                            f"company='{comp_name}' set='{active_set['set_name']}' "
                            f"appended [{validated['priority']} | weight={validated['weight']}] '{validated['text']}'",
                        )
                        self._bot.send_message(
                            chat_id,
                            f"✅ Appended to <b>{html.escape(active_set['set_name'])}</b>:\n"
                            f"<b>[{html.escape(validated['priority'].upper())} | Weight: {validated['weight']}]</b> "
                            f"{html.escape(validated['text'])}",
                        )
                    except ValueError as err:
                        self._bot.send_message(chat_id, f"❌ Invalid rule: {html.escape(str(err))}")
                self._session_store.set_pending_rule_text(chat_id, None)
            self._send_rules_menu(chat_id, comp_name, comp_id)
            return True

        if data == "rule_edit_menu":
            active_set = self._bridge.get_active_rule_set(comp_id)
            rules = active_set.get("rules", []) if active_set else []
            if not rules:
                self._bot.send_message(chat_id, "ℹ️ No rules in this set to update.")
                return True
            self._bot.send_message(
                chat_id,
                f"✏️ <b>Select a rule in {html.escape(active_set['set_name'])} to update:</b>",
                reply_markup=self._keyboards.edit_rules_menu(rules),
            )
            return True

        if data.startswith("rule_edit_pick:"):
            idx = int(data.split(":", 1)[1])
            active_set = self._bridge.get_active_rule_set(comp_id)
            rules = active_set.get("rules", []) if active_set else []
            if not (1 <= idx <= len(rules)):
                self._bot.send_message(chat_id, "⚠️ Rule not found.")
                self._send_rules_menu(chat_id, comp_name, comp_id)
                return True
            rule = rules[idx - 1]
            self._bot.send_message(
                chat_id,
                f"✏️ <b>Updating Rule #{idx}</b>\n\n"
                f"<b>Text:</b> {html.escape(rule['text'])}\n"
                f"<b>Priority:</b> {html.escape(rule['priority'].upper())} (Weight: {rule['weight']})\n\n"
                f"What would you like to change?",
                reply_markup=self._keyboards.edit_rule_action_menu(idx),
            )
            return True

        if data.startswith("rule_edit_text:"):
            idx = int(data.split(":", 1)[1])
            active_set = self._bridge.get_active_rule_set(comp_id)
            rules = active_set.get("rules", []) if active_set else []
            if not (active_set and 1 <= idx <= len(rules)):
                self._bot.send_message(chat_id, "⚠️ Rule not found.")
                self._send_rules_menu(chat_id, comp_name, comp_id)
                return True
            msg = self._bot.send_message(
                chat_id,
                f"✏️ Enter the updated text for Rule #{idx} "
                f"({self.MIN_RULE_LENGTH}-{self.MAX_RULE_LENGTH} characters):\n\n"
                f"<i>Current: {html.escape(rules[idx - 1]['text'])}</i>",
            )
            self._bot.register_next_step_handler(
                msg, self._step_edit_rule_text, comp_name, comp_id, active_set["rule_set_id"], idx
            )
            return True

        if data.startswith("rule_edit_prio:"):
            idx = int(data.split(":", 1)[1])
            active_set = self._bridge.get_active_rule_set(comp_id)
            rules = active_set.get("rules", []) if active_set else []
            if not (1 <= idx <= len(rules)):
                self._bot.send_message(chat_id, "⚠️ Rule not found.")
                self._send_rules_menu(chat_id, comp_name, comp_id)
                return True
            self._bot.send_message(
                chat_id,
                f"⚖️ Select new priority & weight for:\n<i>\"{html.escape(rules[idx - 1]['text'])}\"</i>",
                reply_markup=self._keyboards.edit_rule_priority_menu(idx),
            )
            return True

        if data.startswith("rule_set_prio:"):
            parts = data.split(":", 2)
            idx, new_prio = int(parts[1]), parts[2]
            active_set = self._bridge.get_active_rule_set(comp_id)
            rules = list(active_set.get("rules") or []) if active_set else []
            if active_set and 1 <= idx <= len(rules):
                try:
                    updated_rule = self._validator.validate_and_normalize_rule(rules[idx - 1]["text"], new_prio)
                    rules[idx - 1] = updated_rule
                    self._bridge.update_rule_set(comp_id, active_set["rule_set_id"], rules=rules)
                    self._log_server_event(
                        "RULES",
                        f"company='{comp_name}' set='{active_set['set_name']}' "
                        f"updated rule #{idx} -> [{updated_rule['priority']} | weight={updated_rule['weight']}]",
                    )
                    self._bot.send_message(
                        chat_id,
                        f"✅ Updated Rule #{idx} to <b>[{html.escape(updated_rule['priority'].upper())} | Weight: {updated_rule['weight']}]</b>.",
                    )
                except ValueError as err:
                    self._bot.send_message(chat_id, f"❌ {html.escape(str(err))}")
            self._send_rules_menu(chat_id, comp_name, comp_id)
            return True

        if data == "rule_del_menu":
            active_set = self._bridge.get_active_rule_set(comp_id)
            rules = active_set.get("rules", []) if active_set else []
            if not rules:
                self._bot.send_message(chat_id, "ℹ️ No rules available to delete.")
                return True
            self._bot.send_message(
                chat_id,
                f"Tap a rule in <b>{html.escape(active_set['set_name'])}</b> to delete it:",
                reply_markup=self._keyboards.delete_rules_menu(rules),
            )
            return True

        if data.startswith("rule_del:"):
            idx = int(data.split(":", 1)[1])
            active_set = self._bridge.get_active_rule_set(comp_id)
            rules = list(active_set.get("rules") or []) if active_set else []
            if active_set and 1 <= idx <= len(rules):
                removed = rules.pop(idx - 1)
                self._bridge.update_rule_set(comp_id, active_set["rule_set_id"], rules=rules)
                self._log_server_event(
                    "RULES",
                    f"company='{comp_name}' set='{active_set['set_name']}' deleted '{removed.get('text', '')}'",
                )
                self._bot.send_message(
                    chat_id,
                    f"🗑 Removed Rule: <b>{html.escape(str(removed.get('text', '')))}</b>",
                )
            self._send_rules_menu(chat_id, comp_name, comp_id)
            return True

        if data == "rule_clear":
            active_set = self._bridge.get_active_rule_set(comp_id)
            if active_set:
                self._bridge.update_rule_set(comp_id, active_set["rule_set_id"], rules=[])
                self._log_server_event(
                    "RULES",
                    f"company='{comp_name}' cleared all rules in set '{active_set['set_name']}'.",
                )
                self._bot.send_message(
                    chat_id,
                    f"🧹 Cleared all rules in <b>{html.escape(active_set['set_name'])}</b>.",
                )
            self._send_rules_menu(chat_id, comp_name, comp_id)
            return True

        return False

    # -------------------------------------------------------------------------
    # Telegram Handler Registration
    # -------------------------------------------------------------------------

    def _register_handlers(self) -> None:
        @self._bot.message_handler(commands=["start", "menu", "help"])
        def handle_start(message: Message):
            user_label = message.from_user.username or message.from_user.first_name or str(message.from_user.id)
            self._log_server_event(
                "COMMAND",
                f"/{message.text.lstrip('/').split()[0]} from user={user_label} (id={message.from_user.id})",
            )
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

                upload_info = self._bridge.upload_resume(
                    company_id=comp_id,
                    company_name=comp_name,
                    file_name=doc.file_name,
                    pdf_bytes=pdf_bytes,
                )

                status = upload_info.get("status", "valid")
                pages = upload_info.get("pages", 0)
                reason = html.escape(str(upload_info.get("reason", "")))
                total_resumes = len(self._bridge.list_resumes(comp_id))

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
                self._session_store.clear_active_company(user_id)
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
                return

            if self._handle_rules_callbacks(data, chat_id, comp_name, comp_id):
                return

            # ---- Resume Management ----
            if data == "menu_resumes":
                self._send_resumes_menu(chat_id, comp_name, comp_id)

            elif data == "res_del_menu":
                resumes = self._bridge.list_resumes(comp_id)
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
                resumes = self._bridge.list_resumes(comp_id)
                if 1 <= idx <= len(resumes):
                    target_name = resumes[idx - 1].get("file_name") or resumes[idx - 1].get("file")
                    if target_name and self._bridge.delete_resume(comp_id, target_name):
                        self._log_server_event("RESUMES", f"company='{comp_name}' deleted '{target_name}'")
                        self._bot.send_message(chat_id, f"🗑 Removed Resume: <b>{html.escape(target_name)}</b>")
                self._send_resumes_menu(chat_id, comp_name, comp_id)

            elif data == "res_clear":
                self._bridge.clear_resumes(comp_id)
                self._log_server_event("RESUMES", f"company='{comp_name}' cleared all resumes.")
                self._bot.send_message(chat_id, "🧹 All resumes cleared for this company.")
                self._send_resumes_menu(chat_id, comp_name, comp_id)

            # ---- Top-N Limit Configuration ----
            elif data == "menu_topn":
                resume_count = len(self._bridge.list_resumes(comp_id))
                curr_n = self._session_store.get_effective_top_n(chat_id, resume_count)
                avail_hint = (
                    f"\nUploaded resumes: <b>{resume_count}</b> (max limit: <b>{resume_count}</b>)"
                    if resume_count > 0
                    else "\n<i>No resumes uploaded yet — limit will auto-cap once resumes are added.</i>"
                )
                self._bot.send_message(
                    chat_id,
                    f"🎯 <b>Select Candidate Shortlist Limit (Top N):</b>\n\n"
                    f"Current limit: <b>{curr_n}</b>{avail_hint}",
                    reply_markup=self._keyboards.top_n_menu(curr_n, max_resumes=resume_count),
                )

            elif data == "set_topn_custom":
                resume_count = len(self._bridge.list_resumes(comp_id))
                max_n = resume_count if resume_count > 0 else 100
                msg = self._bot.send_message(
                    chat_id,
                    f"✏️ <b>Enter Custom Top N Limit:</b>\n"
                    f"Send a positive whole number between <code>1</code> and <code>{max_n}</code>:",
                )
                self._bot.register_next_step_handler(msg, self._step_set_custom_topn)

            elif data.startswith("set_topn:"):
                requested_n = int(data.split(":", 1)[1])
                resume_count = len(self._bridge.list_resumes(comp_id))
                effective_n, was_capped = self._validator.cap_top_n(requested_n, resume_count)
                self._session_store.set_top_n(chat_id, effective_n)
                self._log_server_event("CONFIG", f"company='{comp_name}' set top_n={effective_n}")
                if was_capped:
                    self._bot.send_message(
                        chat_id,
                        f"ℹ️ Only <b>{resume_count}</b> resume(s) uploaded — Top N Limit capped to <b>{effective_n}</b>!",
                    )
                else:
                    self._bot.send_message(chat_id, f"🎯 <b>Top N Shortlist Limit set to {effective_n}!</b>")
                self._send_main_dashboard(chat_id, user_id)

            # ---- Screening, Results & Summary (Scoped to Active Rule Set) ----
            elif data == "menu_screen":
                self._trigger_screening(chat_id, user_id, comp_name, comp_id)

            elif data == "menu_results":
                self._send_results_view(chat_id, comp_name, comp_id)

            elif data == "menu_summary":
                self._send_summary_breakdown(chat_id, comp_name, comp_id)

            elif data.startswith("cand_view:"):
                idx = int(data.split(":", 1)[1])
                active_set = self._bridge.get_active_rule_set(comp_id)
                active_set_id = active_set["rule_set_id"] if active_set else None
                results, _ = self._bridge.get_screening_results(comp_id, business_rules_id=active_set_id)
                top_n = self._session_store.get_top_n(chat_id)
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

        requested_n = int(text)
        _, comp_info = self._get_active_company(message.from_user.id)
        resume_count = len(self._bridge.list_resumes(comp_info["company_id"])) if comp_info else 0
        val, was_capped = self._validator.cap_top_n(requested_n, resume_count)

        self._session_store.set_top_n(message.chat.id, val)
        self._log_server_event("CONFIG", f"user={message.from_user.id} set custom top_n={val}")
        if was_capped:
            self._bot.send_message(
                message.chat.id,
                f"ℹ️ Only <b>{resume_count}</b> resume(s) uploaded — Top N Shortlist Limit capped to <b>{val}</b>!",
            )
        else:
            self._bot.send_message(message.chat.id, f"✅ <b>Top N Shortlist Limit set to {val}!</b>")
        self._send_main_dashboard(message.chat.id, message.from_user.id)

    def _step_create_company_name(self, message: Message) -> None:
        try:
            name = self._validator.validate_company_name(message.text or "")
        except ValueError as err:
            self._bot.reply_to(message, f"❌ {html.escape(str(err))} Use /start to try again.")
            return
        msg = self._bot.reply_to(
            message,
            f"🔒 Set a <b>Passcode</b> for <b>{html.escape(name)}</b> (min {self._validator.MIN_PASSCODE_LENGTH} characters):",
        )
        self._bot.register_next_step_handler(msg, self._step_create_company_passcode, name)

    def _step_create_company_passcode(self, message: Message, name: str) -> None:
        try:
            passcode = self._validator.validate_passcode(message.text or "")
        except ValueError as err:
            self._bot.reply_to(message, f"❌ {html.escape(str(err))} Use /start to try again.")
            return

        invite_code = self._validator.generate_invite_code(name)
        passcode_hash = self._validator.hash_passcode(passcode)

        try:
            record = self._bridge.create_company(
                name=name,
                passcode_hash=passcode_hash,
                owner_id=message.from_user.id,
                invite_code=invite_code,
            )
        except Exception as err:
            self._bot.reply_to(message, f"❌ Could not create company: {html.escape(str(err))}")
            return

        comp_id = record["company_id"]
        self._session_store.set_active_company_name(message.from_user.id, record["company_name"])

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
        record = self._bridge.get_company_by_invite(code)
        if not record:
            self._bot.reply_to(message, "❌ Invalid Invite Code. Use /start to try again.")
            return
        msg = self._bot.reply_to(
            message,
            f"🔒 Enter Passcode for <b>{html.escape(record['company_name'])}</b>:",
        )
        self._bot.register_next_step_handler(msg, self._step_join_company_passcode, record)

    def _step_join_company_passcode(self, message: Message, record: Dict[str, Any]) -> None:
        if not self._validator.verify_passcode(message.text or "", record.get("passcode_hash")):
            self._bot.reply_to(message, "❌ Incorrect Passcode. Use /start to try again.")
            return

        comp_name = record["company_name"]
        comp_id = record["company_id"]
        self._bridge.add_company_member(comp_id, comp_name, message.from_user.id)
        self._session_store.set_active_company_name(message.from_user.id, comp_name)

        self._log_server_event("AUTH", f"User {message.from_user.id} joined '{comp_name}' (id=#{comp_id}).")
        self._bot.send_message(message.chat.id, f"✅ Joined <b>{html.escape(comp_name)}</b>!")
        self._send_main_dashboard(message.chat.id, message.from_user.id)

    def _step_create_ruleset_name(self, message: Message, comp_name: str, comp_id: int) -> None:
        set_name = (message.text or "").strip()
        try:
            created = self._bridge.create_rule_set(company_id=comp_id, set_name=set_name, rules=[])
        except ValueError as err:
            self._bot.reply_to(message, f"❌ {html.escape(str(err))}")
            self._send_rules_menu(message.chat.id, comp_name, comp_id)
            return

        self._log_server_event(
            "RULES",
            f"company='{comp_name}' created & activated rule set '{created['set_name']}' (#{created['rule_set_id']})",
        )
        self._bot.send_message(
            message.chat.id,
            f"🆕 Created & activated Rule Set <b>{html.escape(created['set_name'])}</b> "
            f"<code>(ID: #{created['rule_set_id']})</code>!",
        )
        self._send_rules_menu(message.chat.id, comp_name, comp_id)

    def _step_rename_ruleset(
        self,
        message: Message,
        comp_name: str,
        comp_id: int,
        rule_set_id: int,
    ) -> None:
        new_name = (message.text or "").strip()
        try:
            updated = self._bridge.update_rule_set(company_id=comp_id, rule_set_id=rule_set_id, set_name=new_name)
        except ValueError as err:
            self._bot.reply_to(message, f"❌ {html.escape(str(err))}")
            self._send_rules_menu(message.chat.id, comp_name, comp_id)
            return

        self._log_server_event(
            "RULES",
            f"company='{comp_name}' renamed rule set #{rule_set_id} -> '{updated['set_name']}'",
        )
        self._bot.send_message(
            message.chat.id,
            f"✅ Rule Set renamed to <b>{html.escape(updated['set_name'])}</b>!",
        )
        self._send_rules_menu(message.chat.id, comp_name, comp_id)

    def _step_add_rule_text(
        self,
        message: Message,
        comp_name: str,
        comp_id: int,
        rule_set_id: int,
    ) -> None:
        text = (message.text or "").strip()
        if len(text) < self.MIN_RULE_LENGTH or len(text) > self.MAX_RULE_LENGTH:
            self._bot.reply_to(
                message,
                f"❌ Rule must be {self.MIN_RULE_LENGTH}-{self.MAX_RULE_LENGTH} characters.",
            )
            self._send_rules_menu(message.chat.id, comp_name, comp_id)
            return

        active_set = self._bridge.set_active_rule_set(comp_id, rule_set_id) or self._bridge.get_active_rule_set(comp_id)
        existing = active_set.get("rules", []) if active_set else []
        if any(r.get("text", "").lower() == text.lower() for r in existing):
            self._bot.reply_to(message, "❌ That rule is already in this set. Please enter a unique rule.")
            self._send_rules_menu(message.chat.id, comp_name, comp_id)
            return

        self._session_store.set_pending_rule_text(message.chat.id, text)
        self._bot.send_message(
            message.chat.id,
            f"⚖️ Select priority & weight for:\n<i>\"{html.escape(text)}\"</i>",
            reply_markup=self._keyboards.priority_selection_menu(),
        )

    def _step_edit_rule_text(
        self,
        message: Message,
        comp_name: str,
        comp_id: int,
        rule_set_id: int,
        idx: int,
    ) -> None:
        new_text = (message.text or "").strip()
        active_set = self._bridge.set_active_rule_set(comp_id, rule_set_id) or self._bridge.get_active_rule_set(comp_id)
        rules = list(active_set.get("rules") or []) if active_set else []
        if not (active_set and 1 <= idx <= len(rules)):
            self._bot.reply_to(message, "⚠️ Rule set or rule not found.")
            self._send_rules_menu(message.chat.id, comp_name, comp_id)
            return

        if any(i != (idx - 1) and r.get("text", "").lower() == new_text.lower() for i, r in enumerate(rules)):
            self._bot.reply_to(message, "❌ Another rule in this set already has that text.")
            self._send_rules_menu(message.chat.id, comp_name, comp_id)
            return

        try:
            updated = self._validator.validate_and_normalize_rule(new_text, rules[idx - 1]["priority"])
        except ValueError as err:
            self._bot.reply_to(message, f"❌ {html.escape(str(err))}")
            self._send_rules_menu(message.chat.id, comp_name, comp_id)
            return

        rules[idx - 1] = updated
        self._bridge.update_rule_set(comp_id, active_set["rule_set_id"], rules=rules)
        self._log_server_event(
            "RULES",
            f"company='{comp_name}' set='{active_set['set_name']}' edited rule #{idx} text -> '{updated['text']}'",
        )
        self._bot.send_message(
            message.chat.id,
            f"✅ Updated Rule #{idx} <b>[{html.escape(updated['priority'].upper())} | Weight: {updated['weight']}]</b>: "
            f"{html.escape(updated['text'])}",
        )
        self._send_rules_menu(message.chat.id, comp_name, comp_id)

    # -------------------------------------------------------------------------
    # Pipeline & Presentation Delegates (Scoped to Active Rule Set)
    # -------------------------------------------------------------------------

    def _trigger_screening(self, chat_id: int, user_id: int, comp_name: str, comp_id: int) -> None:
        active_set = self._bridge.get_active_rule_set(comp_id)
        if not active_set:
            self._bot.send_message(
                chat_id,
                "⚠️ Please create a Business Rule Set and add at least one rule before running screening!",
                reply_markup=self._keyboards.rules_menu(has_active_set=False, has_rules=False, set_count=0),
            )
            return

        rules = self._validator.normalize_rules_list(active_set.get("rules"))
        if not rules:
            all_sets = self._bridge.list_rule_sets(comp_id)
            self._bot.send_message(
                chat_id,
                f"⚠️ Rule Set <b>{html.escape(active_set['set_name'])}</b> has no rules yet! Append at least one rule first.",
                reply_markup=self._keyboards.rules_menu(
                    has_active_set=True,
                    has_rules=False,
                    set_count=len(all_sets),
                ),
            )
            return

        resumes = self._bridge.list_resumes(comp_id)
        if not resumes:
            self._bot.send_message(
                chat_id,
                "⚠️ No resumes uploaded yet! Send one or more <b>.pdf</b> files in this chat first.",
                reply_markup=self._keyboards.back_to_dashboard(),
            )
            return

        top_n = self._session_store.get_effective_top_n(chat_id, len(resumes))
        active_set_id = active_set["rule_set_id"]
        active_set_name = active_set["set_name"]

        employer_inputs = {
            "company_name": comp_name,
            "company_id": comp_id,
            "business_rules_id": active_set_id,
            "rule_set_name": active_set_name,
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
            f"🚀 <b>Starting AI Screening for {html.escape(comp_name)}</b>\n"
            f"📂 Rule Set: <b>{html.escape(active_set_name)}</b> <code>(ID: #{active_set_id})</code>\n"
            f"• Rules: {len(rules)} | Resumes: {len(resumes)} | Top N: {top_n}",
        )
        self._log_server_event(
            "PIPELINE",
            f"Screening triggered by user={user_id} for '{comp_name}' (#{comp_id}) "
            f"set='{active_set_name}' (#{active_set_id}) [rules={len(rules)}, resumes={len(resumes)}, top_n={top_n}]",
        )

        def on_progress(stage_text: str) -> None:
            self._edit_safe_html(
                chat_id,
                wait_msg.message_id,
                f"⏳ <b>Screening {html.escape(comp_name)} ({html.escape(active_set_name)})...</b>\n\n"
                f"{html.escape(stage_text)}",
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

            self._bridge.save_screening_results(
                comp_id,
                ranked_candidates,
                summary_data,
                filtered_resumes=filtered_resumes,
                business_rules_id=active_set_id,
            )
            self.display_screening_results(ranked_candidates, top_n=top_n)

            self._edit_safe_html(
                chat_id,
                wait_msg.message_id,
                f"✅ <b>AI Screening Complete!</b>\n"
                f"🏢 {html.escape(comp_name)} | 📂 {html.escape(active_set_name)}\n"
                f"Qualified & ranked candidates: <b>{len(ranked_candidates)}</b>",
            )
            self._send_results_view(chat_id, comp_name, comp_id)
        except Exception as err:
            self._log_server_event("ERROR", f"Screening failed for '{comp_name}' ({active_set_name}): {err}")
            self._edit_safe_html(
                chat_id,
                wait_msg.message_id,
                f"❌ Screening failed: {html.escape(str(err))}",
            )

    def _send_results_view(self, chat_id: int, comp_name: str, comp_id: int) -> None:
        active_set = self._bridge.get_active_rule_set(comp_id)
        active_set_id = active_set["rule_set_id"] if active_set else None
        active_set_name = active_set["set_name"] if active_set else None

        results, _ = self._bridge.get_screening_results(comp_id, business_rules_id=active_set_id)
        if not results:
            set_hint = f" for Rule Set <b>{html.escape(active_set_name)}</b>" if active_set_name else ""
            self._bot.send_message(
                chat_id,
                f"ℹ️ No screening results yet{set_hint}.\n"
                f"Tap <b>🚀 Run AI Resume Screening</b> on the dashboard first!",
                reply_markup=self._keyboards.back_to_dashboard(),
            )
            return

        ranked = results[: self._session_store.get_top_n(chat_id)]
        msg = self._formatter.format_results_overview(comp_name, ranked, rule_set_name=active_set_name)
        self._send_safe_html(chat_id, msg, reply_markup=self._keyboards.results_menu(len(ranked)))

    def _send_candidate_pdf(self, chat_id: int, comp_name: str, comp_id: int, idx: int) -> None:
        active_set = self._bridge.get_active_rule_set(comp_id)
        active_set_id = active_set["rule_set_id"] if active_set else None
        results, _ = self._bridge.get_screening_results(comp_id, business_rules_id=active_set_id)
        ranked = results[: self._session_store.get_top_n(chat_id)]

        if not ranked or idx < 1 or idx > len(ranked):
            self._bot.send_message(chat_id, "⚠️ Candidate not found.")
            return

        filename = ranked[idx - 1].get("file", "")
        if not filename:
            self._bot.send_message(chat_id, "❌ Resume filename not available.")
            return

        pdf_bytes = self._bridge.get_resume_pdf_bytes(comp_id, filename)
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

        resumes = self._bridge.list_resumes(comp_id)
        matched = next((r for r in resumes if (r.get("file_name") or r.get("file")) == filename), None)
        if matched and matched.get("pdf_url"):
            self._bot.send_message(
                chat_id,
                f"📄 <b>{html.escape(filename)}</b>\n🔗 Download URL: {html.escape(matched['pdf_url'])}",
            )
            return

        self._bot.send_message(chat_id, f"❌ PDF file '{html.escape(filename)}' not found in storage.")

    def _send_summary_breakdown(self, chat_id: int, comp_name: str, comp_id: int) -> None:
        active_set = self._bridge.get_active_rule_set(comp_id)
        active_set_id = active_set["rule_set_id"] if active_set else None
        active_set_name = active_set["set_name"] if active_set else None
        rules = active_set.get("rules", []) if active_set else []

        results, summary_data = self._bridge.get_screening_results(comp_id, business_rules_id=active_set_id)
        if not results and not summary_data:
            set_hint = f" for Rule Set <b>{html.escape(active_set_name)}</b>" if active_set_name else ""
            self._bot.send_message(
                chat_id,
                f"ℹ️ No summary report yet{set_hint}. Run AI Screening first!",
                reply_markup=self._keyboards.back_to_dashboard(),
            )
            return

        msg = self._formatter.format_summary_report(
            comp_name,
            rules,
            results,
            summary_data=summary_data,
            rule_set_name=active_set_name,
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
        mode = "CLOUD (DataManager)" if self._bridge.use_cloud else "CLOUD STUB (In-Memory)"
        self._log_server_event("SERVER", f"Telegram Bot polling started [{mode}]. Waiting for user messages...")
        self._bot.infinity_polling(timeout=20, long_polling_timeout=10)


if __name__ == "__main__":
    telegram_io = TelegramIOManager()
    telegram_io.start()
