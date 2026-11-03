from typing import Any, Dict, List


class TelegramFormatter:
    """Formats candidate cards, profile details, and AI Summary analytics."""

    @staticmethod
    def format_dashboard(
        company_name: str, invite_code: str, rule_count: int, resume_count: int, top_n: int
    ) -> str:
        return (
            f"🏢 <b>Company Folder:</b> {company_name}\n"
            f"🔑 <b>Team Invite Code:</b> <code>{invite_code}</code>\n\n"
            f"📋 <b>Business Rules:</b> {rule_count} configured\n"
            f"📄 <b>Uploaded Resumes:</b> {resume_count} PDF(s) in folder\n"
            f"🎯 <b>Top N Shortlist Limit:</b> {top_n}\n\n"
            f"<i>💡 Tip: Drag & drop PDF resumes directly into this chat anytime to upload!</i>"
        )

    @staticmethod
    def format_rules_list(company_name: str, rules: List[Dict[str, Any]]) -> str:
        if not rules:
            return f"📋 <b>Business Rules for {company_name}</b>\n\n<i>No business rules configured yet.</i>"
        lines = [f"{i}. <b>[{r.get('priority', 'reject').upper()}]</b> {r.get('text', '')}" for i, r in enumerate(rules, 1)]
        return f"📋 <b>Business Rules for {company_name}</b>\n\n" + "\n".join(lines)

    @staticmethod
    def format_results_overview(company_name: str, ranked: List[Dict[str, Any]]) -> str:
        lines = [f"🏆 <b>TOP {len(ranked)} CANDIDATES ({company_name})</b>\n"]
        for idx, cand in enumerate(ranked, start=1):
            name = cand.get("name") or cand.get("file")
            score = cand.get("score")
            score_str = f"{score:.1f}%" if score is not None else "N/A"
            lines.append(f"<b>#{idx} — {name}</b> ({score_str})\n<i>{cand.get('reason', '')}</i>\n")
        return "\n".join(lines)

    @staticmethod
    def format_candidate_profile(cand: Dict[str, Any], idx: int) -> str:
        skills = ", ".join(cand.get("skills", [])) or "None listed"
        quals = "\n".join(f"  • {q}" for q in cand.get("qualifications", [])) or "None listed"
        exp = "\n".join(f"  • {w}" for w in cand.get("work_experience", [])) or "None listed"

        return (
            f"👤 <b>CANDIDATE PROFILE [Rank #{idx}]</b>\n\n"
            f"<b>Name:</b> {cand.get('name') or cand.get('file')}\n"
            f"<b>File:</b> {cand.get('file')}\n"
            f"<b>Email:</b> {cand.get('email', 'N/A')} | <b>Phone:</b> {cand.get('phone', 'N/A')}\n"
            f"<b>Score:</b> {cand.get('score', 0):.1f}%\n"
            f"<b>Reason:</b> {cand.get('reason', '')}\n\n"
            f"<b>Summary:</b>\n{cand.get('summary', 'No summary')}\n\n"
            f"<b>Skills:</b> {skills}\n\n"
            f"<b>Qualifications:</b>\n{quals}\n\n"
            f"<b>Work Experience:</b>\n{exp}"
        )

    @staticmethod
    def format_summary_report(
        company_name: str, rules: List[Dict[str, Any]], candidates: List[Dict[str, Any]]
    ) -> str:
        """Section 5 Feature: Summary overview & per-rule applicant match breakdown."""
        total = len(candidates)
        accepted = [c for c in candidates if (c.get("score") or 0) > 0]
        rejected = [c for c in candidates if (c.get("score") or 0) == 0]
        invalid = [c for c in candidates if c.get("outcome") == "invalid"]

        scores = [c["score"] for c in accepted if c.get("score") is not None]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
        high_score = round(max(scores), 1) if scores else 0.0
        low_score = round(min(scores), 1) if scores else 0.0

        rule_lines = []
        for idx, rule in enumerate(rules, 1):
            r_text = rule.get("text", "")
            matches = [
                c.get("name", c.get("file"))
                for c in accepted
                if any(r_text.lower() in str(m).lower() for m in c.get("matched_rules", []))
            ]
            pct = round((len(matches) / total * 100), 1) if total > 0 else 0.0
            match_str = f" ({', '.join(matches)})" if matches else ""
            rule_lines.append(
                f"{idx}. <b>[{rule.get('priority', 'reject').upper()}]</b> {r_text}\n"
                f"   ✅ Matched: <b>{len(matches)}/{total}</b> applicants ({pct}%){match_str}"
            )

        rules_section = "\n".join(rule_lines) if rule_lines else "<i>No rules configured.</i>"

        return (
            f"📈 <b>AI SCREENING SUMMARY OVERVIEW ({company_name})</b>\n\n"
            f"<b>1. Applicant Pool Breakdown:</b>\n"
            f"• Total Evaluated: <b>{total}</b>\n"
            f"• Qualifying / Accepted: <b>{len(accepted)}</b>\n"
            f"• Disqualified / Rejected: <b>{len(rejected)}</b>\n"
            f"• Invalid / Unreadable: <b>{len(invalid)}</b>\n\n"
            f"<b>2. Score Metrics (Accepted Pool):</b>\n"
            f"• Average Score: <b>{avg_score:.1f}%</b> | "
            f"Highest: <b>{high_score:.1f}%</b> | Lowest: <b>{low_score:.1f}%</b>\n\n"
            f"<b>3. Business Rules Match Breakdown:</b>\n"
            f"{rules_section}"
        )