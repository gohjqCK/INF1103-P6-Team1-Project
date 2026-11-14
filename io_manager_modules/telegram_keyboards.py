from typing import Any, Dict, List, Optional
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from io_manager_modules.telegram_validator import PRIORITY_WEIGHTS


class TelegramKeyboards:
    """Factory creating inline keyboard markups for the full Telegram Bot application."""

    @staticmethod
    def auth_menu(joined_companies: Optional[List[Dict[str, Any]]] = None) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        for comp in joined_companies or []:
            comp_id = comp.get("company_id")
            comp_name = comp.get("company_name", "Company")
            invite = comp.get("invite_code", "")
            label = f"🏢 Switch to {comp_name} ({invite})" if invite else f"🏢 Switch to {comp_name}"
            kb.add(InlineKeyboardButton(label, callback_data=f"auth_switch:{comp_id}"))
        kb.add(
            InlineKeyboardButton("🏢 Create New Company Folder", callback_data="auth_create"),
            InlineKeyboardButton("🔑 Join Company with Invite Code", callback_data="auth_join"),
        )
        return kb

    @staticmethod
    def cancel_button(callback_data: str = "menu_main", label: str = "❌ Cancel") -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(label, callback_data=callback_data))
        return kb

    @staticmethod
    def confirm_action_menu(
        confirm_callback: str,
        cancel_callback: str,
        confirm_label: str = "✅ Yes, Delete",
    ) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton(confirm_label, callback_data=confirm_callback),
            InlineKeyboardButton("❌ Cancel", callback_data=cancel_callback),
        )
        return kb

    @staticmethod
    def dashboard_menu(
        rule_count: int = 0,
        resume_count: int = 0,
        top_n: int = 3,
        active_set_name: Optional[str] = None,
    ) -> InlineKeyboardMarkup:
        """Full Telegram dashboard: Rule Sets, Resumes, Top-N, Screening, Results, Summary, Switch."""
        rules_label = (
            f"📋 Business Rules [{active_set_name}: {rule_count}]"
            if active_set_name
            else "📋 Manage Business Rule Sets (0)"
        )
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton(rules_label, callback_data="menu_rules"),
            InlineKeyboardButton(f"📁 Manage Resumes ({resume_count})", callback_data="menu_resumes"),
            InlineKeyboardButton(f"🎯 Candidate Shortlist Limit (Top {top_n})", callback_data="menu_topn"),
            InlineKeyboardButton("🚀 Run AI Resume Screening", callback_data="menu_screen"),
            InlineKeyboardButton("🏆 View Screening Results", callback_data="menu_results"),
            InlineKeyboardButton("📈 View AI Summary Report", callback_data="menu_summary"),
            InlineKeyboardButton("🔄 Switch / Logout Company", callback_data="menu_switch"),
        )
        return kb

    @staticmethod
    def rules_menu(
        has_active_set: bool = False,
        has_rules: bool = False,
        set_count: int = 0,
    ) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        if has_active_set:
            kb.add(InlineKeyboardButton("➕ Append New Rule to Set", callback_data="rule_add"))
            if has_rules:
                kb.add(
                    InlineKeyboardButton("✏️ Update / Edit a Rule", callback_data="rule_edit_menu"),
                    InlineKeyboardButton("🗑 Delete a Rule", callback_data="rule_del_menu"),
                    InlineKeyboardButton("🧹 Clear Rules in This Set", callback_data="rule_clear"),
                )
            kb.add(
                InlineKeyboardButton(f"🔀 Swap Active Rule Set ({set_count})", callback_data="ruleset_select_menu"),
                InlineKeyboardButton("🆕 Create New Rule Set", callback_data="ruleset_create"),
                InlineKeyboardButton("✏️ Rename This Rule Set", callback_data="ruleset_rename"),
                InlineKeyboardButton("🗑 Delete This Rule Set", callback_data="ruleset_delete"),
            )
        else:
            kb.add(InlineKeyboardButton("🆕 Create First Rule Set", callback_data="ruleset_create"))

        kb.add(InlineKeyboardButton("⬅️ Back to Dashboard", callback_data="menu_main"))
        return kb

    @staticmethod
    def rule_sets_selection_menu(
        rule_sets: List[Dict[str, Any]],
        active_set_id: Optional[int] = None,
    ) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        for rs in rule_sets:
            rs_id = rs.get("rule_set_id")
            rs_name = str(rs.get("set_name", "Untitled Set"))
            count = len(rs.get("rules") or [])
            prefix = "✅ " if rs_id == active_set_id else "📂 "
            suffix = " [ACTIVE]" if rs_id == active_set_id else ""
            kb.add(
                InlineKeyboardButton(
                    f"{prefix}{rs_name} ({count} rule{'s' if count != 1 else ''}){suffix}",
                    callback_data=f"ruleset_pick:{rs_id}",
                )
            )
        kb.add(InlineKeyboardButton("🆕 Create New Rule Set", callback_data="ruleset_create"))
        kb.add(InlineKeyboardButton("⬅️ Back to Rules Menu", callback_data="menu_rules"))
        return kb

    @staticmethod
    def priority_selection_menu() -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("🔴 Must Have (Weight: 4)", callback_data="rule_prio:must"),
            InlineKeyboardButton("🟠 Important (Weight: 3)", callback_data="rule_prio:important"),
            InlineKeyboardButton("🟢 Nice to Have (Weight: 2)", callback_data="rule_prio:nice"),
            InlineKeyboardButton("🔵 Can Consider (Weight: 1)", callback_data="rule_prio:can consider"),
            InlineKeyboardButton("⛔ Reject / Dealbreaker (Weight: 0)", callback_data="rule_prio:reject"),
            InlineKeyboardButton("❌ Cancel", callback_data="menu_rules"),
        )
        return kb

    @staticmethod
    def edit_rules_menu(rules: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        for idx, rule in enumerate(rules, start=1):
            prio = str(rule.get("priority", "reject")).lower()
            weight = rule.get("weight", PRIORITY_WEIGHTS.get(prio, 0))
            text = str(rule.get("text", ""))
            short_text = text[:24] + ("..." if len(text) > 24 else "")
            kb.add(
                InlineKeyboardButton(
                    f"✏️ #{idx} [{prio.upper()} | W:{weight}] {short_text}",
                    callback_data=f"rule_edit_pick:{idx}",
                )
            )
        kb.add(InlineKeyboardButton("⬅️ Back to Rules Menu", callback_data="menu_rules"))
        return kb

    @staticmethod
    def edit_rule_action_menu(idx: int) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("✏️ Edit Rule Text", callback_data=f"rule_edit_text:{idx}"),
            InlineKeyboardButton("⚖️ Change Priority / Weight", callback_data=f"rule_edit_prio:{idx}"),
            InlineKeyboardButton("⬅️ Back to Rules Menu", callback_data="menu_rules"),
        )
        return kb

    @staticmethod
    def edit_rule_priority_menu(idx: int) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("🔴 Must Have (Weight: 4)", callback_data=f"rule_set_prio:{idx}:must"),
            InlineKeyboardButton("🟠 Important (Weight: 3)", callback_data=f"rule_set_prio:{idx}:important"),
            InlineKeyboardButton("🟢 Nice to Have (Weight: 2)", callback_data=f"rule_set_prio:{idx}:nice"),
            InlineKeyboardButton("🔵 Can Consider (Weight: 1)", callback_data=f"rule_set_prio:{idx}:can consider"),
            InlineKeyboardButton("⛔ Reject / Dealbreaker (Weight: 0)", callback_data=f"rule_set_prio:{idx}:reject"),
            InlineKeyboardButton("⬅️ Cancel", callback_data="menu_rules"),
        )
        return kb

    @staticmethod
    def delete_rules_menu(rules: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        for idx, rule in enumerate(rules, start=1):
            prio = str(rule.get("priority", "reject")).lower()
            weight = rule.get("weight", PRIORITY_WEIGHTS.get(prio, 0))
            text = str(rule.get("text", ""))
            short_text = text[:24] + ("..." if len(text) > 24 else "")
            kb.add(
                InlineKeyboardButton(
                    f"🗑 #{idx} [{prio.upper()} | W:{weight}] {short_text}",
                    callback_data=f"rule_del:{idx}",
                )
            )
        kb.add(InlineKeyboardButton("⬅️ Back to Rules Menu", callback_data="menu_rules"))
        return kb

    @staticmethod
    def resumes_menu(has_resumes: bool = False) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        if has_resumes:
            kb.add(
                InlineKeyboardButton("🗑 Delete a Resume", callback_data="res_del_menu"),
                InlineKeyboardButton("🧹 Clear All Resumes", callback_data="res_clear"),
            )
        kb.add(InlineKeyboardButton("⬅️ Back to Dashboard", callback_data="menu_main"))
        return kb

    @staticmethod
    def delete_resumes_menu(resumes: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        for idx, res in enumerate(resumes, start=1):
            fname = str(res.get("file_name") or res.get("file") or f"Resume #{idx}")
            short_name = fname[:30] + ("..." if len(fname) > 30 else "")
            kb.add(
                InlineKeyboardButton(
                    f"🗑 #{idx} {short_name}",
                    callback_data=f"res_del:{idx}",
                )
            )
        kb.add(InlineKeyboardButton("⬅️ Back to Resumes", callback_data="menu_resumes"))
        return kb

    @staticmethod
    def top_n_menu(current_top_n: int = 3, max_resumes: Optional[int] = None) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=2)
        base_presets = [1, 3, 5, 10]
        if max_resumes is not None and max_resumes > 0:
            presets = [val for val in base_presets if val <= max_resumes]
            if max_resumes not in presets and max_resumes <= 100:
                presets.append(max_resumes)
            presets.sort()
        else:
            presets = base_presets

        buttons = [
            InlineKeyboardButton(
                f"{'✅ ' if val == current_top_n else ''}Top {val}",
                callback_data=f"set_topn:{val}",
            )
            for val in presets
        ]
        kb.add(*buttons)
        kb.add(InlineKeyboardButton("✏️ Enter Custom Number", callback_data="set_topn_custom"))
        kb.add(InlineKeyboardButton("⬅️ Back to Dashboard", callback_data="menu_main"))
        return kb

    @staticmethod
    def results_menu(ranked_count: int) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=2)
        for idx in range(1, ranked_count + 1):
            kb.add(
                InlineKeyboardButton(f"👤 Profile #{idx}", callback_data=f"cand_view:{idx}"),
                InlineKeyboardButton(f"📥 PDF #{idx}", callback_data=f"cand_pdf:{idx}"),
            )
        kb.add(InlineKeyboardButton("📈 View AI Summary Report", callback_data="menu_summary"))
        kb.add(InlineKeyboardButton("⬅️ Back to Dashboard", callback_data="menu_main"))
        return kb

    @staticmethod
    def candidate_profile_menu(idx: int) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("📥 Download PDF", callback_data=f"cand_pdf:{idx}"),
            InlineKeyboardButton("⬅️ Back to Results", callback_data="menu_results"),
        )
        return kb

    @staticmethod
    def back_to_dashboard() -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("⬅️ Back to Dashboard", callback_data="menu_main"))
        return kb
