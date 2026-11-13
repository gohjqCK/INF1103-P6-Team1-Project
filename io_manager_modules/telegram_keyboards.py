from typing import Any, Dict, List
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup


class TelegramKeyboards:
    """Factory creating inline keyboard markups for the full Telegram Bot application."""

    @staticmethod
    def auth_menu() -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("🏢 Create New Company Folder", callback_data="auth_create"),
            InlineKeyboardButton("🔑 Join Company with Invite Code", callback_data="auth_join"),
        )
        return kb

    @staticmethod
    def dashboard_menu(
        rule_count: int = 0,
        resume_count: int = 0,
        top_n: int = 3,
    ) -> InlineKeyboardMarkup:
        """Full Telegram dashboard: Rules, Resumes, Top-N, Screening, Results, Summary, Switch."""
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton(f"📋 Manage Business Rules ({rule_count})", callback_data="menu_rules"),
            InlineKeyboardButton(f"📁 Manage Resumes ({resume_count})", callback_data="menu_resumes"),
            InlineKeyboardButton(f"🎯 Candidate Shortlist Limit (Top {top_n})", callback_data="menu_topn"),
            InlineKeyboardButton("🚀 Run AI Resume Screening", callback_data="menu_screen"),
            InlineKeyboardButton("🏆 View Screening Results", callback_data="menu_results"),
            InlineKeyboardButton("📈 View AI Summary Report", callback_data="menu_summary"),
            InlineKeyboardButton("🔄 Switch / Logout Company", callback_data="menu_switch"),
        )
        return kb

    @staticmethod
    def rules_menu(has_rules: bool = True) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("➕ Add New Rule", callback_data="rule_add"))
        if has_rules:
            kb.add(
                InlineKeyboardButton("🗑 Delete a Rule", callback_data="rule_del_menu"),
                InlineKeyboardButton("🧹 Clear All Rules", callback_data="rule_clear"),
            )
        kb.add(InlineKeyboardButton("⬅️ Back to Dashboard", callback_data="menu_main"))
        return kb

    @staticmethod
    def priority_selection_menu() -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("🔴 Must Have (Weight: 4)", callback_data="rule_prio:must"),
            InlineKeyboardButton("🟠 Important (Weight: 3)", callback_data="rule_prio:important"),
            InlineKeyboardButton("🟢 Nice to Have (Weight: 2)", callback_data="rule_prio:nice"),
            InlineKeyboardButton("🔵 Can Consider (Weight: 1)", callback_data="rule_prio:can consider"),
            InlineKeyboardButton("⛔ Reject / Dealbreaker (No Weight)", callback_data="rule_prio:reject"),
            InlineKeyboardButton("❌ Cancel", callback_data="menu_rules"),
        )
        return kb

    @staticmethod
    def delete_rules_menu(rules: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        for idx, rule in enumerate(rules, start=1):
            prio = str(rule.get("priority", "reject")).upper()
            text = str(rule.get("text", ""))
            short_text = text[:28] + ("..." if len(text) > 28 else "")
            kb.add(
                InlineKeyboardButton(
                    f"🗑 #{idx} [{prio}] {short_text}",
                    callback_data=f"rule_del:{idx}",
                )
            )
        kb.add(InlineKeyboardButton("⬅️ Back to Rules", callback_data="menu_rules"))
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
    def top_n_menu(current_top_n: int = 3) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=2)
        presets = [1, 3, 5, 10]
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
