import html
from typing import Any, Dict, List, Optional


PRIORITY_WEIGHTS: Dict[str, int] = {
    "must": 4,
    "important": 3,
    "nice": 2,
    "can consider": 1,
    "reject": 0,
}


def _esc(value: Any) -> str:
    """Escapes text safely for Telegram HTML parse mode."""
    return html.escape(str(value if value is not None else ""))


class TelegramFormatter:
    """Formats dashboard, rule sets, resumes, candidate cards, profile details, and AI Summary reports for Telegram."""

    @staticmethod
    def format_dashboard(
        company_name: str,
        invite_code: str,
        company_id: int,
        resume_count: int,
        rule_count: int = 0,
        top_n: int = 3,
        has_results: bool = False,
        active_set_name: Optional[str] = None,
    ) -> str:
        status_text = "✅ Results Available" if has_results else "⏳ Not Run Yet"
        set_line = (
            f"📂 <b>Active Rule Set:</b> {_esc(active_set_name)} ({rule_count} rule(s))"
            if active_set_name
            else "📂 <b>Active Rule Set:</b> <i>None created yet</i>"
        )
        return (
            f"🏢 <b>Company Folder:</b> {_esc(company_name)} <code>(ID: #{company_id})</code>\n"
            f"🔑 <b>Team Invite Code:</b> <code>{_esc(invite_code)}</code>\n\n"
            f"{set_line}\n"
            f"📁 <b>Uploaded Resumes:</b> {resume_count} PDF(s)\n"
            f"🎯 <b>Shortlist Limit:</b> Top {top_n}\n"
            f"📊 <b>Screening Status:</b> {status_text}\n\n"
            f"📤 <b>Upload Resumes Anytime:</b>\n"
            f"Drag & drop or attach any <b>.pdf</b> resume directly into this chat to add it to your company.\n\n"
            f"<i>Use the buttons below to manage rule sets, upload resumes, and run AI screening!</i>"
        )

    @staticmethod
    def format_rules_list(
        company_name: str,
        active_set: Optional[Dict[str, Any]],
        all_sets: List[Dict[str, Any]],
    ) -> str:
        if not active_set:
            return (
                f"📋 <b>BUSINESS RULE SETS ({_esc(company_name)})</b>\n\n"
                f"<i>No business rule sets created yet.</i>\n\n"
                f"Create a named set for each role (e.g. <code>Finance</code>, <code>Cleaners</code>) "
                f"to begin adding weighted screening criteria."
            )

        set_name = str(active_set.get("set_name", "Default"))
        set_id = active_set.get("rule_set_id", "N/A")
        rules = active_set.get("rules") or []

        sets_summary = ", ".join(
            f"<b>{_esc(rs.get('set_name'))}</b>" if rs.get("rule_set_id") == set_id else _esc(rs.get("set_name"))
            for rs in all_sets
        ) or _esc(set_name)

        header = (
            f"📋 <b>BUSINESS RULES — {_esc(company_name)}</b>\n"
            f"📂 <b>Active Set:</b> {_esc(set_name)} <code>(ID: #{set_id})</code>\n"
            f"🗂 <b>Company Sets ({len(all_sets)}):</b> {sets_summary}\n"
        )

        if not rules:
            return (
                f"{header}\n"
                f"<i>This rule set has no rules yet.</i>\n\n"
                f"Tap <b>➕ Append New Rule to Set</b> below to add criteria."
            )

        badge_map = {
            "must": "🔴 MUST",
            "important": "🟠 IMPORTANT",
            "nice": "🟢 NICE",
            "can consider": "🔵 CAN CONSIDER",
            "reject": "⛔ REJECT",
        }
        lines = [header]
        for idx, rule in enumerate(rules, start=1):
            prio_raw = str(rule.get("priority", "reject")).lower()
            weight = rule.get("weight", PRIORITY_WEIGHTS.get(prio_raw, 0))
            badge = badge_map.get(prio_raw, f"[{_esc(prio_raw.upper())}]")
            text = _esc(rule.get("text", "<unspecified>"))
            lines.append(f"{idx}. <b>{badge} (Weight: {weight})</b> — {text}")
        return "\n".join(lines)

    @staticmethod
    def format_resumes_list(company_name: str, resumes: List[Dict[str, Any]]) -> str:
        header = f"📁 <b>RESUMES FOR {_esc(company_name)} ({len(resumes)})</b>\n"
        if not resumes:
            return (
                f"{header}\n"
                f"<i>No resumes uploaded yet.</i>\n\n"
                f"Drag & drop or attach <b>.pdf</b> files directly into this chat to upload!"
            )

        lines = [header]
        for idx, res in enumerate(resumes, start=1):
            fname = _esc(res.get("file_name") or res.get("file") or f"Resume #{idx}")
            status = str(res.get("status", "valid")).lower()
            badge = "✅" if status == "valid" else "⚠️"
            pages = res.get("pages", 0)
            pages_str = f" ({pages}p)" if pages else ""
            source = _esc(res.get("source", "Cloud / Session"))
            reason = res.get("reason", "")
            reason_str = f"\n    <i>Reason: {_esc(reason)}</i>" if status != "valid" and reason else ""
            lines.append(f"{idx}. {badge} <b>{fname}</b>{pages_str} — <i>{source}</i>{reason_str}")
        lines.append("\n<i>Tip: Send more .pdf files anytime in chat to add them.</i>")
        return "\n".join(lines)

    @staticmethod
    def format_results_overview(
        company_name: str,
        ranked: List[Dict[str, Any]],
        rule_set_name: Optional[str] = None,
    ) -> str:
        scope = f"{_esc(company_name)} | {_esc(rule_set_name)}" if rule_set_name else _esc(company_name)
        lines = [f"🏆 <b>SCREENING RESULTS ({scope}) — {len(ranked)} Candidate(s)</b>\n"]
        for idx, cand in enumerate(ranked, start=1):
            name = _esc(cand.get("name") or cand.get("file") or f"Candidate #{idx}")
            score = cand.get("score")
            score_str = f"{float(score):.1f}%" if score is not None else "N/A"
            reason = _esc(cand.get("reason", ""))
            lines.append(f"<b>#{idx} — {name}</b> ({score_str})\n<i>{reason}</i>\n")
        return "\n".join(lines)

    @staticmethod
    def format_candidate_profile(cand: Dict[str, Any], idx: int) -> str:
        skills_list = cand.get("skills") or []
        skills = _esc(", ".join(str(s) for s in skills_list)) if skills_list else "None listed"

        quals_list = cand.get("qualifications") or []
        quals = "\n".join(f"  • {_esc(q)}" for q in quals_list) if quals_list else "None listed"

        exp_list = cand.get("work_experience") or []
        exp = "\n".join(f"  • {_esc(w)}" for w in exp_list) if exp_list else "None listed"

        score = cand.get("score")
        score_str = f"{float(score):.1f}%" if score is not None else "N/A"

        return (
            f"👤 <b>CANDIDATE PROFILE [Rank #{idx}]</b>\n\n"
            f"<b>Name:</b> {_esc(cand.get('name') or cand.get('file'))}\n"
            f"<b>File:</b> {_esc(cand.get('file'))}\n"
            f"<b>Email:</b> {_esc(cand.get('email') or 'N/A')} | <b>Phone:</b> {_esc(cand.get('phone') or 'N/A')}\n"
            f"<b>Score:</b> {score_str}\n"
            f"<b>Reason:</b> {_esc(cand.get('reason', ''))}\n\n"
            f"<b>Summary:</b>\n{_esc(cand.get('summary') or 'No summary')}\n\n"
            f"<b>Skills:</b> {skills}\n\n"
            f"<b>Qualifications:</b>\n{quals}\n\n"
            f"<b>Work Experience:</b>\n{exp}"
        )

    @staticmethod
    def format_ai_summary_json(
        company_name: str,
        summary_data: Dict[str, Any],
        rule_set_name: Optional[str] = None,
    ) -> str:
        """Formats the structured summary dictionary generated by AIManager.create_summary()."""
        totals = summary_data.get("totals", {})
        scores = summary_data.get("score_statistics") or summary_data.get("scores", {})
        rules = summary_data.get("rule_statistics") or summary_data.get("rules", [])
        top_candidates = summary_data.get("top_candidates", [])
        overall_summary = _esc(summary_data.get("overall_summary", "No AI narrative available."))

        rule_lines = []
        for idx, r in enumerate(rules, 1):
            prio = str(r.get("priority", "rule")).lower()
            weight = r.get("weight", PRIORITY_WEIGHTS.get(prio, 0))
            text = _esc(r.get("rule") or r.get("text", ""))
            met = r.get("met") if "met" in r else r.get("met_count", 0)
            if "missed" in r:
                checked = met + r.get("missed", 0)
            else:
                checked = r.get("checked_count", 0)
            rate = r.get("percent_met") if "percent_met" in r else r.get("met_rate", 0.0)
            checked_str = f"/{checked}" if checked else ""
            rule_lines.append(
                f"{idx}. <b>[{_esc(prio.upper())} | W:{weight}]</b> {text}\n"
                f"   ✅ Met: <b>{met}{checked_str}</b> ({float(rate):.1f}%)"
            )
        rules_section = "\n".join(rule_lines) if rule_lines else "<i>No rules recorded in summary.</i>"

        top_lines = []
        for idx, c in enumerate(top_candidates, 1):
            rank = c.get("rank", idx)
            name = _esc(c.get("name") or c.get("file") or "Unknown")
            score = c.get("score")
            score_str = f"{float(score):.1f}%" if score is not None else "N/A"
            reason = _esc(c.get("reason", ""))
            reason_str = f" — <i>{reason}</i>" if reason else ""
            top_lines.append(f"• <b>#{rank} {name}</b> ({score_str}){reason_str}")
        top_section = "\n".join(top_lines) if top_lines else "<i>No qualifying candidates.</i>"

        avg_score = scores.get("average")
        high_score = scores.get("highest")
        low_score = scores.get("lowest")
        avg_str = f"{float(avg_score):.1f}%" if avg_score is not None else "N/A"
        high_str = f"{float(high_score):.1f}%" if high_score is not None else "N/A"
        low_str = f"{float(low_score):.1f}%" if low_score is not None else "N/A"

        total_resumes = totals.get("processed", totals.get("resumes", 0))
        scope = f"{_esc(company_name)} | {_esc(rule_set_name)}" if rule_set_name else _esc(company_name)

        return (
            f"📈 <b>RESUM-AI SUMMARY REPORT ({scope})</b>\n\n"
            f"<b>1. Executive AI Narrative:</b>\n"
            f"<i>{overall_summary}</i>\n\n"
            f"<b>2. Applicant Pool Breakdown:</b>\n"
            f"• Total Resumes: <b>{total_resumes}</b>\n"
            f"• Qualifying / Scored: <b>{totals.get('scored', 0)}</b>\n"
            f"• Disqualified / Rejected: <b>{totals.get('rejected', 0)}</b>\n"
            f"• Invalid / Unreadable: <b>{totals.get('invalid', 0)}</b>\n\n"
            f"<b>3. Score Metrics (Scored Pool):</b>\n"
            f"• Average: <b>{avg_str}</b> | "
            f"Highest: <b>{high_str}</b> | "
            f"Lowest: <b>{low_str}</b>\n\n"
            f"<b>4. Top Shortlisted Candidates:</b>\n"
            f"{top_section}\n\n"
            f"<b>5. Per-Rule Match Breakdown:</b>\n"
            f"{rules_section}"
        )

    @staticmethod
    def format_summary_report(
        company_name: str,
        rules: List[Dict[str, Any]],
        candidates: List[Dict[str, Any]],
        summary_data: Optional[Dict[str, Any]] = None,
        rule_set_name: Optional[str] = None,
    ) -> str:
        """Formats summary report using structured summary data if available, or computes from candidates list."""
        if summary_data and isinstance(summary_data, dict) and "totals" in summary_data:
            return TelegramFormatter.format_ai_summary_json(
                company_name,
                summary_data,
                rule_set_name=rule_set_name,
            )

        total = len(candidates)
        accepted = [c for c in candidates if (c.get("score") or 0) > 0]
        rejected = [c for c in candidates if (c.get("score") or 0) == 0 and c.get("outcome") != "invalid"]
        invalid = [c for c in candidates if c.get("outcome") == "invalid"]

        scores = [float(c["score"]) for c in accepted if c.get("score") is not None]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
        high_score = round(max(scores), 1) if scores else 0.0
        low_score = round(min(scores), 1) if scores else 0.0

        rule_lines = []
        for idx, rule in enumerate(rules, 1):
            r_text = str(rule.get("text", ""))
            prio = str(rule.get("priority", "reject")).lower()
            weight = rule.get("weight", PRIORITY_WEIGHTS.get(prio, 0))
            matches = [
                str(c.get("name") or c.get("file") or "Candidate")
                for c in accepted
                if any(r_text.lower() in str(m).lower() for m in c.get("matched_rules", []))
            ]
            pct = round((len(matches) / total * 100), 1) if total > 0 else 0.0
            match_str = f" ({_esc(', '.join(matches))})" if matches else ""
            rule_lines.append(
                f"{idx}. <b>[{_esc(prio.upper())} | W:{weight}]</b> {_esc(r_text)}\n"
                f"   ✅ Matched: <b>{len(matches)}/{total}</b> applicants ({pct}%){match_str}"
            )

        rules_section = "\n".join(rule_lines) if rule_lines else "<i>No rules configured.</i>"
        scope = f"{_esc(company_name)} | {_esc(rule_set_name)}" if rule_set_name else _esc(company_name)

        return (
            f"📈 <b>RESUM-AI SUMMARY OVERVIEW ({scope})</b>\n\n"
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
