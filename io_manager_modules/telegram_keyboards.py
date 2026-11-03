from typing import Any, Dict, List
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup


class TelegramKeyboards:
    """Factory creating inline keyboard markups for the Telegram bot."""

    @staticmethod
    def auth_menu() -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("🏢 Create New Company Folder", callback_data="auth_create"),
            InlineKeyboardButton("🔑 Join Company with Invite Code", callback_data="auth_join"),
        )
        return kb

    @staticmethod
    def dashboard_menu(top_n: int = 3) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("📋 Manage Rules", callback_data="menu_rules"),
            InlineKeyboardButton("📁 View Resumes", callback_data="menu_resumes"),
            InlineKeyboardButton(f"🎯 Set Top N ({top_n})", callback_data="menu_topn"),
            InlineKeyboardButton("📊 Saved Results", callback_data="menu_results"),
        )
        kb.add(InlineKeyboardButton("📈 AI Summary & Rule Breakdown", callback_data="menu_summary"))
        kb.add(InlineKeyboardButton("🚀 Run AI Resume Screening", callback_data="menu_screen"))
        kb.add(InlineKeyboardButton("🔄 Switch Company Folder", callback_data="menu_switch"))
        return kb

    @staticmethod
    def rules_menu() -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("➕ Add Rule", callback_data="rule_add"),
            InlineKeyboardButton("🗑 Delete a Rule", callback_data="rule_del_menu"),
            InlineKeyboardButton("🧹 Clear All Rules", callback_data="rule_clear"),
            InlineKeyboardButton("⬅️ Back to Dashboard", callback_data="menu_main"),
        )
        return kb

    @staticmethod
    def priority_selection_menu() -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("1️⃣ Must (Weight: 4)", callback_data="rule_prio:must"),
            InlineKeyboardButton("2️⃣ Important (Weight: 3)", callback_data="rule_prio:important"),
            InlineKeyboardButton("3️⃣ Nice (Weight: 2)", callback_data="rule_prio:nice"),
            InlineKeyboardButton("4️⃣ Can Consider (Weight: 1)", callback_data="rule_prio:can consider"),
            InlineKeyboardButton("🚫 Reject / Knockout Rule", callback_data="rule_prio:reject"),
        )
        return kb

    @staticmethod
    def delete_rules_menu(rules: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        for idx, r in enumerate(rules, 1):
            prio = r.get("priority", "reject").upper()
            text_preview = r.get("text", "")[:30]
            kb.add(InlineKeyboardButton(f"❌ #{idx}: [{prio}] {text_preview}", callback_data=f"rule_del:{idx}"))
        kb.add(InlineKeyboardButton("⬅️ Cancel", callback_data="menu_rules"))
        return kb

    @staticmethod
    def top_n_menu() -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=4)
        kb.add(*[InlineKeyboardButton(str(n), callback_data=f"set_topn:{n}") for n in [1, 3, 5, 10]])
        kb.add(InlineKeyboardButton("✏️ Custom Number", callback_data="set_topn_custom"))
        kb.add(InlineKeyboardButton("⬅️ Back", callback_data="menu_main"))
        return kb

    @staticmethod
    def results_menu(ranked_count: int) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=2)
        for idx in range(1, ranked_count + 1):
            kb.add(
                InlineKeyboardButton(f"👤 Profile #{idx}", callback_data=f"cand_view:{idx}"),
                InlineKeyboardButton(f"📥 PDF #{idx}", callback_data=f"cand_pdf:{idx}"),
            )
        kb.add(InlineKeyboardButton("📈 AI Summary & Rule Breakdown", callback_data="menu_summary"))
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
