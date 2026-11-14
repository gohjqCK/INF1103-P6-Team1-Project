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
import re
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from io_manager_modules.io_manager_base import BaseIOManager
from io_manager_modules.telegram_data_bridge import BridgeStorageError, TelegramDataBridge
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
    from telebot.types import BotCommand, CallbackQuery, Message
    _TELEBOT_AVAILABLE = True
except ImportError:
    telebot = None
    BotCommand = None
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
    MAX_TELEGRAM_PDF_BYTES = 20 * 1024 * 1024
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
        self._screening_lock = threading.Lock()
        self._screening_companies: set[str] = set()

        if not _TELEBOT_AVAILABLE:
            self._bot = None
            self._log_server_event("ERROR", "pyTelegramBotAPI not installed. Run 'pip install pyTelegramBotAPI'.")
            return

        self._bot = telebot.TeleBot(self._token, parse_mode="HTML")
        self._register_handlers()
        self._register_bot_commands()

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
        is_logged_out_fn = getattr(self._session_store, "is_logged_out", None)
        allow_fallback = not is_logged_out_fn(user_id) if callable(is_logged_out_fn) else True
        comp_name, comp_info = self._bridge.resolve_user_company(
            user_id,
            active_name=active_name,
            allow_fallback=allow_fallback,
        )
        if comp_name and comp_name != active_name:
            self._session_store.set_active_company_name(user_id, comp_name)
        return comp_name, comp_info

    def _send_safe_html(
        self,
        chat_id: int,
        text: str,
        reply_markup: Any = None,
    ) -> None:
        chunks: List[str] = []
        current = ""
        for line in (text or "").splitlines(keepends=True):
            if len(line) > 3900:
                if current:
                    chunks.append(current)
                    current = ""
                for start in range(0, len(line), 3900):
                    chunks.append(line[start : start + 3900])
            elif len(current) + len(line) > 3900:
                chunks.append(current)
                current = line
            else:
                current += line
        if current or not chunks:
            chunks.append(current)

        for idx, chunk in enumerate(chunks):
            markup = reply_markup if idx == len(chunks) - 1 else None
            try:
                self._bot.send_message(chat_id, chunk, reply_markup=markup)
            except Exception as err:
                self._log_server_event("ERROR", f"Telegram HTML send failed (chat={chat_id}): {err}")
                plain_chunk = html.unescape(re.sub(r"<[^>]+>", "", chunk))
                try:
                    self._bot.send_message(chat_id, plain_chunk, parse_mode=None, reply_markup=markup)
                except Exception as fallback_err:
                    self._log_server_event("ERROR", f"Telegram plain-text fallback failed (chat={chat_id}): {fallback_err}")

    def _edit_safe_html(self, chat_id: int, message_id: int, text: str) -> None:
        try:
            self._bot.edit_message_text(text, chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    def _delete_message_safe(self, chat_id: int, message_id: Optional[int]) -> None:
        if not self._bot or message_id is None:
            return
        try:
            self._bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    def _clear_pending_steps(self, chat_id: int) -> None:
        if not self._bot:
            return
        try:
            if hasattr(self._bot, "clear_step_handler_by_chat_id"):
                self._bot.clear_step_handler_by_chat_id(chat_id)
        except Exception:
            pass

    def _register_bot_commands(self) -> None:
        if not self._bot or BotCommand is None:
            return
        try:
            if hasattr(self._bot, "set_my_commands"):
                self._bot.set_my_commands(
                    [
                        BotCommand("start", "Open RESUM-AI dashboard or sign in"),
                        BotCommand("menu", "Return to the main menu"),
                        BotCommand("help", "Show usage guide and commands"),
                    ]
                )
        except Exception:
            pass

    def _get_joined_companies_safe(self, user_id: int) -> List[Dict[str, Any]]:
        list_fn = getattr(self._bridge, "list_user_companies", None)
        if not callable(list_fn):
            return []
        try:
            result = list_fn(user_id)
            return result if isinstance(result, list) else []
        except Exception:
            return []

    def _answer_callback_safe(self, call_id: str) -> None:
        try:
            self._bot.answer_callback_query(call_id)
        except Exception as err:
            self._log_server_event("ERROR", f"Callback acknowledgement failed: {err}")

    def _notify_user_error(
        self,
        chat_id: int,
        context: str,
        err: Exception,
        reply_to_message: Any = None,
    ) -> None:
        self._log_server_event("ERROR", f"{context}: {err}")
        body = f"❌ <b>{html.escape(context)}:</b> {html.escape(str(err))}"
        try:
            if reply_to_message is not None:
                self._bot.reply_to(reply_to_message, body)
            else:
                self._bot.send_message(chat_id, body)
        except Exception as send_err:
            self._log_server_event("ERROR", f"Failed to send error notification to chat={chat_id}: {send_err}")

    # -------------------------------------------------------------------------
    # UI Presentations
    # -------------------------------------------------------------------------

    def _send_main_dashboard(self, chat_id: int, user_id: int) -> None:
        comp_name, comp_info = self._get_active_company(user_id)
        if not comp_name or not comp_info:
            joined_companies = self._get_joined_companies_safe(user_id)
            self._bot.send_message(
                chat_id,
                "<b>Welcome to RESUM-AI!</b>\n\n"
                "Create a new Company Folder, join your team's folder, or pick one you've already joined:",
                reply_markup=self._keyboards.auth_menu(joined_companies=joined_companies),
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
                reply_markup=self._keyboards.cancel_button("menu_rules"),
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
            set_id = self._validator.parse_callback_int(data)
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
                reply_markup=self._keyboards.cancel_button("menu_rules"),
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
            rule_count = len(active_set.get("rules", []))
            self._bot.send_message(
                chat_id,
                f"⚠️ <b>Confirm Rule Set Deletion</b>\n\n"
                f"Delete Rule Set <b>{html.escape(active_set['set_name'])}</b> ({rule_count} rule(s))?\n"
                "<i>This cannot be undone.</i>",
                reply_markup=self._keyboards.confirm_action_menu(
                    f"ruleset_delete_confirm:{active_set['rule_set_id']}",
                    "menu_rules",
                    confirm_label="✅ Yes, Delete Set",
                ),
            )
            return True

        if data.startswith("ruleset_delete_confirm:"):
            set_id = self._validator.parse_callback_int(data)
            target_set = next(
                (rs for rs in self._bridge.list_rule_sets(comp_id) if rs.get("rule_set_id") == set_id),
                None,
            )
            if not target_set:
                self._bot.send_message(chat_id, "⚠️ Rule Set not found.")
                self._send_rules_menu(chat_id, comp_name, comp_id)
                return True
            deleted_name = target_set["set_name"]
            if self._bridge.delete_rule_set(comp_id, set_id):
                self._log_server_event(
                    "RULES",
                    f"company='{comp_name}' deleted rule set '{deleted_name}' (#{set_id})",
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
                reply_markup=self._keyboards.cancel_button("menu_rules"),
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
            idx = self._validator.parse_callback_int(data)
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
                reply_markup=self._keyboards.cancel_button("menu_rules"),
            )
            self._bot.register_next_step_handler(
                msg, self._step_edit_rule_text, comp_name, comp_id, active_set["rule_set_id"], idx
            )
            return True

        if data.startswith("rule_edit_prio:"):
            idx = self._validator.parse_callback_int(data)
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
            if len(parts) < 3:
                raise ValueError(f"Malformed priority callback '{data}'.")
            idx = self._validator.parse_callback_int(data, part_index=1)
            new_prio = parts[2]
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
            idx = self._validator.parse_callback_int(data)
            active_set = self._bridge.get_active_rule_set(comp_id)
            rules = list(active_set.get("rules") or []) if active_set else []
            if active_set and 1 <= idx <= len(rules):
                target_rule = rules[idx - 1]
                self._bot.send_message(
                    chat_id,
                    f"⚠️ <b>Confirm Rule Deletion</b>\n\n"
                    f"Delete rule #{idx}: <b>{html.escape(str(target_rule.get('text', '')))}</b>?",
                    reply_markup=self._keyboards.confirm_action_menu(
                        f"rule_del_confirm:{idx}",
                        "rule_del_cancel",
                        confirm_label="✅ Yes, Delete Rule",
                    ),
                )
                return True
            self._bot.send_message(chat_id, "⚠️ Rule not found.")
            self._send_rules_menu(chat_id, comp_name, comp_id)
            return True

        if data.startswith("rule_del_confirm:"):
            idx = self._validator.parse_callback_int(data)
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
            else:
                self._bot.send_message(chat_id, "⚠️ Rule not found.")
            self._send_rules_menu(chat_id, comp_name, comp_id)
            return True

        if data == "rule_del_cancel":
            self._send_rules_menu(chat_id, comp_name, comp_id)
            return True

        if data == "rule_clear":
            active_set = self._bridge.get_active_rule_set(comp_id)
            rules = active_set.get("rules", []) if active_set else []
            if not active_set or not rules:
                self._bot.send_message(chat_id, "ℹ️ There are no rules to clear in the active Rule Set.")
                self._send_rules_menu(chat_id, comp_name, comp_id)
                return True
            self._bot.send_message(
                chat_id,
                f"⚠️ <b>Confirm Clear All Rules</b>\n\n"
                f"Remove all <b>{len(rules)}</b> rule(s) from <b>{html.escape(active_set['set_name'])}</b>?",
                reply_markup=self._keyboards.confirm_action_menu(
                    "rule_clear_confirm",
                    "menu_rules",
                    confirm_label="✅ Yes, Clear All",
                ),
            )
            return True

        if data == "rule_clear_confirm":
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
            try:
                self._clear_pending_steps(message.chat.id)
                user_label = message.from_user.username or message.from_user.first_name or str(message.from_user.id)
                cmd_word = (message.text or "/start").lstrip("/").split()[0].split("@")[0].lower()
                self._log_server_event(
                    "COMMAND",
                    f"/{cmd_word} from user={user_label} (id={message.from_user.id})",
                )
                if cmd_word == "help":
                    comp_name, comp_info = self._get_active_company(message.from_user.id)
                    markup = (
                        self._keyboards.back_to_dashboard()
                        if comp_name and comp_info
                        else self._keyboards.auth_menu(
                            joined_companies=self._get_joined_companies_safe(message.from_user.id)
                        )
                    )
                    self._bot.send_message(
                        message.chat.id,
                        self._formatter.format_help_guide(),
                        reply_markup=markup,
                    )
                    return
                self._send_main_dashboard(message.chat.id, message.from_user.id)
            except Exception as err:
                self._notify_user_error(message.chat.id, "Could not load dashboard", err, reply_to_message=message)

        @self._bot.message_handler(content_types=["document"])
        def handle_pdf_upload(message: Message):
            self._clear_pending_steps(message.chat.id)
            try:
                comp_name, comp_info = self._get_active_company(message.from_user.id)
            except Exception as err:
                self._notify_user_error(message.chat.id, "Could not resolve company", err, reply_to_message=message)
                return

            if not comp_name or not comp_info:
                self._bot.reply_to(message, "⚠️ Create or join a Company Folder first using /start.")
                return

            doc = getattr(message, "document", None)
            if doc is None or not getattr(doc, "file_name", None) or not doc.file_name.lower().endswith(".pdf"):
                self._bot.reply_to(message, "❌ Only <b>.pdf</b> files are accepted.")
                return

            file_size = getattr(doc, "file_size", None)
            if isinstance(file_size, int) and file_size > self.MAX_TELEGRAM_PDF_BYTES:
                self._bot.reply_to(
                    message,
                    f"❌ <b>{html.escape(doc.file_name)}</b> exceeds Telegram's 20 MB bot download limit.",
                )
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
                if not getattr(file_info, "file_path", None):
                    raise ValueError("Telegram did not return a downloadable file path.")
                pdf_bytes = self._bot.download_file(file_info.file_path)
                if not pdf_bytes:
                    raise ValueError("Downloaded PDF file is empty (0 bytes).")

                upload_info = self._bridge.upload_resume(
                    company_id=comp_id,
                    company_name=comp_name,
                    file_name=doc.file_name,
                    pdf_bytes=pdf_bytes,
                )

                stored_fname = upload_info.get("file_name") or doc.file_name
                safe_fname = html.escape(stored_fname)
                status = upload_info.get("status", "valid")
                pages = upload_info.get("pages", 0)
                reason = html.escape(str(upload_info.get("reason", "")))
                total_resumes = upload_info.get("total_resumes")
                if total_resumes is None:
                    total_resumes = len(self._bridge.list_resumes(comp_id))

                self._log_server_event(
                    "UPLOAD",
                    f"company='{comp_name}' (#{comp_id}) file='{stored_fname}' status={status} pages={pages} total={total_resumes}",
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
                err_msg = html.escape(str(err))
                if "duplicate" in str(err).lower():
                    msg_text = f"⚠️ <b>Duplicate upload rejected</b>\n<i>{err_msg}</i>"
                else:
                    msg_text = f"❌ Upload failed: {err_msg}"
                self._edit_safe_html(
                    message.chat.id,
                    status_msg.message_id,
                    msg_text,
                )

        @self._bot.message_handler(content_types=["text"])
        def handle_text_message(message: Message):
            try:
                self._bot.reply_to(
                    message,
                    "📤 Send a <b>.pdf</b> resume here to upload it, or tap /menu to open your dashboard.",
                )
            except Exception as err:
                self._log_server_event("ERROR", f"Failed to reply to text message: {err}")

        @self._bot.callback_query_handler(func=lambda call: True)
        def handle_callbacks(call: CallbackQuery):
            chat_id = call.message.chat.id
            user_id = call.from_user.id
            data = call.data or ""
            self._answer_callback_safe(call.id)
            self._clear_pending_steps(chat_id)

            try:
                if data == "auth_create":
                    msg = self._bot.send_message(
                        chat_id,
                        "🏢 Enter your new <b>Company Name</b>:",
                        reply_markup=self._keyboards.cancel_button("auth_cancel"),
                    )
                    self._bot.register_next_step_handler(msg, self._step_create_company_name)
                    return

                if data == "auth_join":
                    msg = self._bot.send_message(
                        chat_id,
                        "🔑 Enter your team's <b>Invite Code</b>:",
                        reply_markup=self._keyboards.cancel_button("auth_cancel"),
                    )
                    self._bot.register_next_step_handler(msg, self._step_join_company_code)
                    return

                if data == "auth_cancel":
                    self._send_main_dashboard(chat_id, user_id)
                    return

                if data.startswith("auth_switch:"):
                    target_comp_id = self._validator.parse_callback_int(data)
                    switch_fn = getattr(self._bridge, "switch_user_company", None)
                    switched = switch_fn(user_id, target_comp_id) if callable(switch_fn) else None
                    if not switched:
                        self._bot.send_message(
                            chat_id,
                            "⚠️ Could not switch to that company folder. Please rejoin using its invite code.",
                            reply_markup=self._keyboards.auth_menu(
                                joined_companies=self._get_joined_companies_safe(user_id)
                            ),
                        )
                        return
                    self._session_store.set_active_company_name(user_id, switched["company_name"])
                    self._log_server_event(
                        "AUTH",
                        f"User {user_id} quick-switched to company '{switched['company_name']}' (#{switched['company_id']}).",
                    )
                    self._send_main_dashboard(chat_id, user_id)
                    return

                if data == "menu_switch":
                    self._session_store.clear_active_company(user_id)
                    self._log_server_event("AUTH", f"User {user_id} opened Switch/Logout menu.")
                    self._bot.send_message(
                        chat_id,
                        "🔄 <b>Switch or Authenticate Company Folder:</b>",
                        reply_markup=self._keyboards.auth_menu(
                            joined_companies=self._get_joined_companies_safe(user_id)
                        ),
                    )
                    return

                comp_name, comp_info = self._get_active_company(user_id)
                if not comp_name or not comp_info:
                    self._bot.send_message(
                        chat_id,
                        "Please create or join a company folder first:",
                        reply_markup=self._keyboards.auth_menu(
                            joined_companies=self._get_joined_companies_safe(user_id)
                        ),
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
                    idx = self._validator.parse_callback_int(data)
                    resumes = self._bridge.list_resumes(comp_id)
                    if 1 <= idx <= len(resumes):
                        target_name = resumes[idx - 1].get("file_name") or resumes[idx - 1].get("file") or f"Resume #{idx}"
                        self._bot.send_message(
                            chat_id,
                            f"⚠️ <b>Confirm Resume Deletion</b>\n\nDelete <b>{html.escape(target_name)}</b>?",
                            reply_markup=self._keyboards.confirm_action_menu(
                                f"res_del_confirm:{idx}",
                                "menu_resumes",
                                confirm_label="✅ Yes, Delete Resume",
                            ),
                        )
                    else:
                        self._bot.send_message(chat_id, "⚠️ Resume not found.")
                        self._send_resumes_menu(chat_id, comp_name, comp_id)

                elif data.startswith("res_del_confirm:"):
                    idx = self._validator.parse_callback_int(data)
                    resumes = self._bridge.list_resumes(comp_id)
                    if 1 <= idx <= len(resumes):
                        target_name = resumes[idx - 1].get("file_name") or resumes[idx - 1].get("file")
                        if target_name and self._bridge.delete_resume(comp_id, target_name):
                            self._log_server_event("RESUMES", f"company='{comp_name}' deleted '{target_name}'")
                            self._bot.send_message(chat_id, f"🗑 Removed Resume: <b>{html.escape(target_name)}</b>")
                    self._send_resumes_menu(chat_id, comp_name, comp_id)

                elif data == "res_clear":
                    resumes = self._bridge.list_resumes(comp_id)
                    if not resumes:
                        self._bot.send_message(chat_id, "ℹ️ There are no resumes to clear.")
                        self._send_resumes_menu(chat_id, comp_name, comp_id)
                    else:
                        self._bot.send_message(
                            chat_id,
                            f"⚠️ <b>Confirm Clear All Resumes</b>\n\n"
                            f"Delete all <b>{len(resumes)}</b> uploaded resume(s) for <b>{html.escape(comp_name)}</b>?\n"
                            "<i>This cannot be undone.</i>",
                            reply_markup=self._keyboards.confirm_action_menu(
                                "res_clear_confirm",
                                "menu_resumes",
                                confirm_label="✅ Yes, Clear All",
                            ),
                        )

                elif data == "res_clear_confirm":
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
                        reply_markup=self._keyboards.cancel_button("menu_main"),
                    )
                    self._bot.register_next_step_handler(msg, self._step_set_custom_topn)

                elif data.startswith("set_topn:"):
                    requested_n = self._validator.parse_callback_int(data)
                    resume_count = len(self._bridge.list_resumes(comp_id))
                    effective_n, was_capped = self._validator.cap_top_n(requested_n, resume_count)
                    self._session_store.set_top_n(chat_id, effective_n)
                    self._log_server_event("CONFIG", f"company='{comp_name}' set top_n={effective_n}")
                    if was_capped:
                        if resume_count > 0 and requested_n > resume_count:
                            cap_note = (
                                f"ℹ️ Only <b>{resume_count}</b> resume(s) uploaded — "
                                f"Top N Limit capped to <b>{effective_n}</b>!"
                            )
                        else:
                            cap_note = (
                                f"ℹ️ Maximum Top N Limit is <b>100</b> — "
                                f"requested <b>{requested_n}</b> was capped to <b>{effective_n}</b>!"
                            )
                        self._bot.send_message(chat_id, cap_note)
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
                    idx = self._validator.parse_callback_int(data)
                    active_set = self._bridge.get_active_rule_set(comp_id)
                    active_set_id = active_set["rule_set_id"] if active_set else None
                    results, _ = self._bridge.get_screening_results(comp_id, business_rules_id=active_set_id)
                    resumes = self._bridge.list_resumes(comp_id)
                    top_n = (
                        self._session_store.get_effective_top_n(chat_id, len(resumes))
                        if len(resumes) > 0
                        else self._session_store.get_top_n(chat_id)
                    )
                    ranked = results[:top_n]
                    if 1 <= idx <= len(ranked):
                        msg = self._formatter.format_candidate_profile(ranked[idx - 1], idx)
                        self._send_safe_html(chat_id, msg, reply_markup=self._keyboards.candidate_profile_menu(idx))
                    else:
                        self._bot.send_message(chat_id, "⚠️ Candidate profile not found. Re-open results.")

                elif data.startswith("cand_pdf:"):
                    idx = self._validator.parse_callback_int(data)
                    self._send_candidate_pdf(chat_id, comp_name, comp_id, idx)
            except (ValueError, BridgeStorageError) as err:
                self._notify_user_error(chat_id, "Action failed", err)
            except Exception as err:
                self._notify_user_error(chat_id, "Unexpected error processing request", err)

    # -------------------------------------------------------------------------
    # Conversational Step Handlers
    # -------------------------------------------------------------------------

    def _handle_step_slash_command(self, message: Message) -> bool:
        """Intercepts slash commands while a step handler is active and aborts the step cleanly."""
        raw_text = (message.text or "").strip()
        if not raw_text.startswith("/"):
            return False
        self._clear_pending_steps(message.chat.id)
        cmd_word = raw_text.lstrip("/").split()[0].split("@")[0].lower()
        if cmd_word == "help":
            comp_name, comp_info = self._get_active_company(message.from_user.id)
            markup = (
                self._keyboards.back_to_dashboard()
                if comp_name and comp_info
                else self._keyboards.auth_menu(
                    joined_companies=self._get_joined_companies_safe(message.from_user.id)
                )
            )
            self._bot.send_message(
                message.chat.id,
                self._formatter.format_help_guide(),
                reply_markup=markup,
            )
            return True
        self._send_main_dashboard(message.chat.id, message.from_user.id)
        return True

    def _step_set_custom_topn(self, message: Message) -> None:
        if self._handle_step_slash_command(message):
            return
        text = (message.text or "").strip()
        if not text.isdigit() or int(text) < 1:
            msg = self._bot.reply_to(
                message,
                "❌ <b>Invalid input!</b> Please send a positive number greater than 0 (e.g. 2, 5, 10):",
                reply_markup=self._keyboards.cancel_button("menu_main"),
            )
            self._bot.register_next_step_handler(msg, self._step_set_custom_topn)
            return

        try:
            requested_n = int(text)
            _, comp_info = self._get_active_company(message.from_user.id)
            resume_count = len(self._bridge.list_resumes(comp_info["company_id"])) if comp_info else 0
            val, was_capped = self._validator.cap_top_n(requested_n, resume_count)

            self._session_store.set_top_n(message.chat.id, val)
            self._log_server_event("CONFIG", f"user={message.from_user.id} set custom top_n={val}")
            if was_capped:
                if resume_count > 0 and requested_n > resume_count:
                    cap_note = (
                        f"ℹ️ Only <b>{resume_count}</b> resume(s) uploaded — "
                        f"Top N Shortlist Limit capped to <b>{val}</b>!"
                    )
                else:
                    cap_note = (
                        f"ℹ️ Maximum Top N Limit is <b>100</b> — "
                        f"requested <b>{requested_n}</b> was capped to <b>{val}</b>!"
                    )
                self._bot.send_message(message.chat.id, cap_note)
            else:
                self._bot.send_message(message.chat.id, f"✅ <b>Top N Shortlist Limit set to {val}!</b>")
            self._send_main_dashboard(message.chat.id, message.from_user.id)
        except Exception as err:
            self._notify_user_error(message.chat.id, "Could not update Top N limit", err, reply_to_message=message)

    def _step_create_company_name(self, message: Message) -> None:
        if self._handle_step_slash_command(message):
            return
        try:
            name = self._validator.validate_company_name(message.text or "")
        except ValueError as err:
            msg = self._bot.reply_to(
                message,
                f"❌ {html.escape(str(err))}\nPlease enter a valid <b>Company Name</b>:",
                reply_markup=self._keyboards.cancel_button("auth_cancel"),
            )
            self._bot.register_next_step_handler(msg, self._step_create_company_name)
            return
        msg = self._bot.reply_to(
            message,
            f"🔒 Set a <b>Passcode</b> for <b>{html.escape(name)}</b> (min {self._validator.MIN_PASSCODE_LENGTH} characters):\n"
            "<i>Your passcode message will be deleted immediately for security.</i>",
            reply_markup=self._keyboards.cancel_button("auth_cancel"),
        )
        self._bot.register_next_step_handler(msg, self._step_create_company_passcode, name)

    def _step_create_company_passcode(self, message: Message, name: str) -> None:
        if self._handle_step_slash_command(message):
            return
        raw_passcode = message.text or ""
        self._delete_message_safe(message.chat.id, getattr(message, "message_id", None))
        try:
            passcode = self._validator.validate_passcode(raw_passcode)
        except ValueError as err:
            msg = self._bot.send_message(
                message.chat.id,
                f"❌ {html.escape(str(err))}\n"
                f"🔒 Enter a <b>Passcode</b> for <b>{html.escape(name)}</b> (min {self._validator.MIN_PASSCODE_LENGTH} characters):",
                reply_markup=self._keyboards.cancel_button("auth_cancel"),
            )
            self._bot.register_next_step_handler(msg, self._step_create_company_passcode, name)
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
            self._bot.send_message(message.chat.id, f"❌ Could not create company: {html.escape(str(err))}")
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
        if self._handle_step_slash_command(message):
            return
        code = (message.text or "").strip().upper()
        try:
            record = self._bridge.get_company_by_invite(code)
        except Exception as err:
            self._notify_user_error(message.chat.id, "Invite lookup failed", err, reply_to_message=message)
            return

        if not record:
            msg = self._bot.reply_to(
                message,
                "❌ Invalid Invite Code. Please enter a valid <b>Invite Code</b>:",
                reply_markup=self._keyboards.cancel_button("auth_cancel"),
            )
            self._bot.register_next_step_handler(msg, self._step_join_company_code)
            return
        msg = self._bot.reply_to(
            message,
            f"🔒 Enter Passcode for <b>{html.escape(record['company_name'])}</b>:\n"
            "<i>Your passcode message will be deleted immediately for security.</i>",
            reply_markup=self._keyboards.cancel_button("auth_cancel"),
        )
        self._bot.register_next_step_handler(msg, self._step_join_company_passcode, record)

    def _step_join_company_passcode(self, message: Message, record: Dict[str, Any]) -> None:
        if self._handle_step_slash_command(message):
            return
        raw_passcode = message.text or ""
        self._delete_message_safe(message.chat.id, getattr(message, "message_id", None))
        if not self._validator.verify_passcode(raw_passcode, record.get("passcode_hash")):
            msg = self._bot.send_message(
                message.chat.id,
                f"❌ Incorrect Passcode. Please try again for <b>{html.escape(record['company_name'])}</b>:",
                reply_markup=self._keyboards.cancel_button("auth_cancel"),
            )
            self._bot.register_next_step_handler(msg, self._step_join_company_passcode, record)
            return

        comp_name = record["company_name"]
        comp_id = record["company_id"]
        try:
            self._bridge.add_company_member(comp_id, comp_name, message.from_user.id)
        except Exception as err:
            self._notify_user_error(message.chat.id, "Could not join company", err)
            return

        self._session_store.set_active_company_name(message.from_user.id, comp_name)
        self._log_server_event("AUTH", f"User {message.from_user.id} joined '{comp_name}' (id=#{comp_id}).")
        self._bot.send_message(message.chat.id, f"✅ Joined <b>{html.escape(comp_name)}</b>!")
        self._send_main_dashboard(message.chat.id, message.from_user.id)

    def _step_create_ruleset_name(self, message: Message, comp_name: str, comp_id: int) -> None:
        if self._handle_step_slash_command(message):
            return
        set_name = (message.text or "").strip()
        if not set_name or len(set_name) > 80:
            msg = self._bot.reply_to(
                message,
                "❌ Rule Set name must be 1-80 characters. Please enter a valid name:",
                reply_markup=self._keyboards.cancel_button("menu_rules"),
            )
            self._bot.register_next_step_handler(msg, self._step_create_ruleset_name, comp_name, comp_id)
            return
        try:
            created = self._bridge.create_rule_set(company_id=comp_id, set_name=set_name, rules=[])
        except ValueError as err:
            msg = self._bot.reply_to(
                message,
                f"❌ {html.escape(str(err))}\nPlease enter another Rule Set name:",
                reply_markup=self._keyboards.cancel_button("menu_rules"),
            )
            self._bot.register_next_step_handler(msg, self._step_create_ruleset_name, comp_name, comp_id)
            return
        except Exception as err:
            self._notify_user_error(message.chat.id, "Could not create Rule Set", err, reply_to_message=message)
            try:
                self._send_rules_menu(message.chat.id, comp_name, comp_id)
            except Exception:
                pass
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
        if self._handle_step_slash_command(message):
            return
        new_name = (message.text or "").strip()
        if not new_name or len(new_name) > 80:
            msg = self._bot.reply_to(
                message,
                "❌ Rule Set name must be 1-80 characters. Please enter a valid name:",
                reply_markup=self._keyboards.cancel_button("menu_rules"),
            )
            self._bot.register_next_step_handler(msg, self._step_rename_ruleset, comp_name, comp_id, rule_set_id)
            return
        try:
            updated = self._bridge.update_rule_set(company_id=comp_id, rule_set_id=rule_set_id, set_name=new_name)
        except ValueError as err:
            msg = self._bot.reply_to(
                message,
                f"❌ {html.escape(str(err))}\nPlease enter another Rule Set name:",
                reply_markup=self._keyboards.cancel_button("menu_rules"),
            )
            self._bot.register_next_step_handler(msg, self._step_rename_ruleset, comp_name, comp_id, rule_set_id)
            return
        except Exception as err:
            self._notify_user_error(message.chat.id, "Could not rename Rule Set", err, reply_to_message=message)
            try:
                self._send_rules_menu(message.chat.id, comp_name, comp_id)
            except Exception:
                pass
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
        if self._handle_step_slash_command(message):
            return
        text = (message.text or "").strip()
        if len(text) < self.MIN_RULE_LENGTH or len(text) > self.MAX_RULE_LENGTH:
            msg = self._bot.reply_to(
                message,
                f"❌ Rule must be {self.MIN_RULE_LENGTH}-{self.MAX_RULE_LENGTH} characters. Please enter your rule again:",
                reply_markup=self._keyboards.cancel_button("menu_rules"),
            )
            self._bot.register_next_step_handler(msg, self._step_add_rule_text, comp_name, comp_id, rule_set_id)
            return

        try:
            active_set = self._bridge.set_active_rule_set(comp_id, rule_set_id) or self._bridge.get_active_rule_set(comp_id)
        except Exception as err:
            self._notify_user_error(message.chat.id, "Could not load Rule Set", err, reply_to_message=message)
            return

        existing = active_set.get("rules", []) if active_set else []
        if any(r.get("text", "").lower() == text.lower() for r in existing):
            msg = self._bot.reply_to(
                message,
                "❌ That rule is already in this set. Please enter a unique rule:",
                reply_markup=self._keyboards.cancel_button("menu_rules"),
            )
            self._bot.register_next_step_handler(msg, self._step_add_rule_text, comp_name, comp_id, rule_set_id)
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
        if self._handle_step_slash_command(message):
            return
        new_text = (message.text or "").strip()
        if len(new_text) < self.MIN_RULE_LENGTH or len(new_text) > self.MAX_RULE_LENGTH:
            msg = self._bot.reply_to(
                message,
                f"❌ Rule must be {self.MIN_RULE_LENGTH}-{self.MAX_RULE_LENGTH} characters. Please enter the updated rule:",
                reply_markup=self._keyboards.cancel_button("menu_rules"),
            )
            self._bot.register_next_step_handler(msg, self._step_edit_rule_text, comp_name, comp_id, rule_set_id, idx)
            return
        try:
            active_set = self._bridge.set_active_rule_set(comp_id, rule_set_id) or self._bridge.get_active_rule_set(comp_id)
            rules = list(active_set.get("rules") or []) if active_set else []
            if not (active_set and 1 <= idx <= len(rules)):
                self._bot.reply_to(message, "⚠️ Rule set or rule not found.")
                self._send_rules_menu(message.chat.id, comp_name, comp_id)
                return

            if any(i != (idx - 1) and r.get("text", "").lower() == new_text.lower() for i, r in enumerate(rules)):
                msg = self._bot.reply_to(
                    message,
                    "❌ Another rule in this set already has that text. Please enter a unique rule:",
                    reply_markup=self._keyboards.cancel_button("menu_rules"),
                )
                self._bot.register_next_step_handler(msg, self._step_edit_rule_text, comp_name, comp_id, rule_set_id, idx)
                return

            updated = self._validator.validate_and_normalize_rule(new_text, rules[idx - 1]["priority"])
            rules[idx - 1] = updated
            self._bridge.update_rule_set(comp_id, active_set["rule_set_id"], rules=rules)
        except Exception as err:
            self._notify_user_error(message.chat.id, "Could not update rule", err, reply_to_message=message)
            try:
                self._send_rules_menu(message.chat.id, comp_name, comp_id)
            except Exception:
                pass
            return

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
        with self._screening_lock:
            if comp_name in self._screening_companies:
                self._bot.send_message(
                    chat_id,
                    f"⏳ A screening run is already in progress for <b>{html.escape(comp_name)}</b>. Please wait for it to finish.",
                    reply_markup=self._keyboards.back_to_dashboard(),
                )
                return
            self._screening_companies.add(comp_name)

        try:
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
        finally:
            with self._screening_lock:
                self._screening_companies.discard(comp_name)

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

        resumes = self._bridge.list_resumes(comp_id)
        top_n = (
            self._session_store.get_effective_top_n(chat_id, len(resumes))
            if len(resumes) > 0
            else self._session_store.get_top_n(chat_id)
        )
        ranked = results[:top_n]
        msg = self._formatter.format_results_overview(comp_name, ranked, rule_set_name=active_set_name)
        self._send_safe_html(chat_id, msg, reply_markup=self._keyboards.results_menu(len(ranked)))

    def _send_candidate_pdf(self, chat_id: int, comp_name: str, comp_id: int, idx: int) -> None:
        try:
            active_set = self._bridge.get_active_rule_set(comp_id)
            active_set_id = active_set["rule_set_id"] if active_set else None
            results, _ = self._bridge.get_screening_results(comp_id, business_rules_id=active_set_id)
            resumes = self._bridge.list_resumes(comp_id)
        except Exception as err:
            self._notify_user_error(chat_id, "Could not load candidate PDF", err)
            return

        top_n = (
            self._session_store.get_effective_top_n(chat_id, len(resumes))
            if len(resumes) > 0
            else self._session_store.get_top_n(chat_id)
        )
        ranked = results[:top_n]
        if not ranked or idx < 1 or idx > len(ranked):
            self._bot.send_message(chat_id, "⚠️ Candidate not found.")
            return

        filename = ranked[idx - 1].get("file", "")
        if not filename:
            self._bot.send_message(chat_id, "❌ Resume filename not available.")
            return

        try:
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
        except Exception as err:
            self._log_server_event("ERROR", f"Direct PDF send failed for '{filename}': {err}")

        try:
            resumes = self._bridge.list_resumes(comp_id)
            matched = next((r for r in resumes if (r.get("file_name") or r.get("file")) == filename), None)
            if matched and matched.get("pdf_url"):
                self._bot.send_message(
                    chat_id,
                    f"📄 <b>{html.escape(filename)}</b>\n🔗 Download URL: {html.escape(matched['pdf_url'])}",
                )
                return
        except Exception as err:
            self._notify_user_error(chat_id, f"Could not retrieve '{filename}'", err)
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
        try:
            self._bot.infinity_polling(timeout=20, long_polling_timeout=10)
        except KeyboardInterrupt:
            self._log_server_event("SERVER", "Polling interrupted by operator.")
            raise
        except Exception as err:
            self._log_server_event("ERROR", f"Telegram polling terminated unexpectedly: {err}")
            raise RuntimeError(f"Telegram polling failed: {err}") from err


if __name__ == "__main__":
    telegram_io = TelegramIOManager()
    telegram_io.start()
