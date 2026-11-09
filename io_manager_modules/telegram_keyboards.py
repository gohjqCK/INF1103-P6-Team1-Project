from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup


class TelegramKeyboards:
    """Factory creating inline keyboard markups for the streamlined Telegram Companion Bot."""

    @staticmethod
    def auth_menu() -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("🏢 Create New Company Folder", callback_data="auth_create"),
            InlineKeyboardButton("🔑 Join Company with Invite Code", callback_data="auth_join"),
        )
        return kb

    @staticmethod
    def dashboard_menu() -> InlineKeyboardMarkup:
        """Streamlined companion dashboard: Upload PDFs, View Resumes, View Results & AI Summary."""
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("📁 View Uploaded Cloud Resumes", callback_data="menu_resumes"),
            InlineKeyboardButton("📊 View Screening Results", callback_data="menu_results"),
            InlineKeyboardButton("📈 View AI Summary Report", callback_data="menu_summary"),
            InlineKeyboardButton("🔄 Switch Company Folder", callback_data="menu_switch"),
        )
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
