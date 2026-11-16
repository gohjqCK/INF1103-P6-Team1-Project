"""Keeps the AI's candidate summary consistent with the scorer's results."""
import re

from ai_manager_modules.ai_manager_text_matcher import TextMatcher


class SummaryReconciler:
    """Stops a candidate summary from claiming skills for rules the scorer marked as missed."""

    _STOPWORDS = TextMatcher.GENERAL_WORDS | {
        "with", "such", "from", "into", "using", "than", "this", "that", "least",
        "must", "should", "able", "work", "working", "hands", "about",
    }

    def reconcile(
        self,
        summary: str,
        rules_met: list[str],
        rules_missed: list[str],
        rules: list[dict],
    ) -> str:
        """Prevents candidate_info.summary from claiming skills or rules that the scorer marked missed."""
        if not summary or not rules_missed:
            return summary

        rule_by_text = {str(r.get("text", "")): r for r in (rules or [])}
        met_tokens = set()
        for r_text in rules_met:
            rule = rule_by_text.get(r_text, {})
            for kw in rule.get("keywords", []):
                met_tokens.update(re.findall(r"[a-z0-9]+", str(kw).lower()))
            for tok in re.findall(r"[a-z0-9]+", r_text.lower()):
                if len(tok) >= 3 and tok not in self._STOPWORDS:
                    met_tokens.add(tok)

        cleaned = summary
        unmatched_notes = []
        for missed_text in rules_missed:
            rule = rule_by_text.get(missed_text, {})
            candidates = set()
            for kw in rule.get("keywords", []):
                for tok in re.findall(r"[a-z0-9]+", str(kw).lower()):
                    if len(tok) >= 3 and tok not in self._STOPWORDS and tok not in met_tokens:
                        candidates.add(tok)
            for tok in re.findall(r"[a-z0-9]+", missed_text.lower()):
                if len(tok) >= 3 and tok not in self._STOPWORDS and tok not in met_tokens:
                    candidates.add(tok)

            contradicted = False
            for tok in sorted(candidates, key=len, reverse=True):
                if re.search(rf"\b{re.escape(tok)}\b", cleaned, re.IGNORECASE):
                    contradicted = True
                    conj_pat = re.compile(
                        rf"(?:\s+and\s+|,\s*)(?:(?!\band\b)[^.,;\n])*?\b{re.escape(tok)}\b[^.,;\n]*",
                        re.IGNORECASE,
                    )
                    cleaned = conj_pat.sub(
                        lambda m: m.group(0)
                        if any(re.search(rf"\b{re.escape(mt)}\b", m.group(0).lower()) for mt in met_tokens)
                        else "",
                        cleaned,
                    )
            if contradicted and any(
                re.search(rf"\b{re.escape(tok)}\b", cleaned, re.IGNORECASE) for tok in candidates
            ):
                unmatched_notes.append(missed_text)

        cleaned = re.sub(r"\s{2,}", " ", cleaned).replace(" ,", ",").replace(" .", ".").strip()
        cleaned = re.sub(r",\s*([.!?])", r"\1", cleaned)
        if unmatched_notes:
            note = "Note: Did not meet requirement(s): " + "; ".join(unmatched_notes) + "."
            if cleaned and not cleaned.endswith((".", "!", "?")):
                cleaned += "."
            cleaned = f"{cleaned} {note}".strip()
        return cleaned
