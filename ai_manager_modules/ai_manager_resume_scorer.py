"""Works out a resume's score from the AI's checks, trusting only what the resume really says."""
import re

from ai_manager_modules.ai_manager_text_matcher import TextMatcher


class ResumeScorer:
    """Scores resumes against one set of rules. A rule counts only if it can be proven from the resume text."""

    _PRIORITY_WEIGHTS = {"must": 4, "important": 3, "nice": 2, "can consider": 1}
    _KNOCKOUT = "reject"
    _NEGATION_WORDS = {"no", "not", "without", "never", "clean", "free", "none", "zero", "neither"}
    _GENERIC_TOKENS = {
        "experience", "years", "year", "skills", "skill", "has", "have", "knowledge",
        "knows", "know", "certification", "certifications", "certified", "record",
        "records", "related", "field", "good", "strong", "hands", "with", "for",
        "and", "the", "using", "use", "work", "working", "database", "databases",
        "system", "systems", "tool", "tools", "schema", "schemas", "ability",
    }

    def __init__(self, rules: list[dict]):
        self._rules = rules

    def score(self, checks: list[dict], resume_text: str) -> dict:
        """Returns the score, any knockout rules that were hit, and the reason as text."""
        matcher = TextMatcher(resume_text)
        proven, unproven = self._verify_ai_answers(checks, matcher)
        self._add_exact_word_matches(proven, unproven, matcher)
        return self._build_result(proven, unproven)

    def _verify_ai_answers(self, checks: list[dict], matcher: TextMatcher) -> tuple[list[int], list[int]]:
        """Splits the rules the AI said yes to into those with real evidence and those without."""
        proven = []
        unproven = []
        for check in checks:
            if not check["shows"]:
                continue
            rule = self._rules[check["id"] - 1]
            keywords = rule.get("keywords", [])
            is_negated_ko = (
                rule.get("priority") == self._KNOCKOUT
                and self._is_negated_evidence(check["evidence"], keywords)
            )
            if not is_negated_ko and self._evidence_is_valid(check["evidence"], keywords, matcher):
                proven.append(check["id"])
            else:
                unproven.append(check["id"])
        return proven, unproven

    @classmethod
    def _is_negated_evidence(cls, evidence: str, keywords: list[str]) -> bool:
        """Returns True if matched knockout keywords in evidence are preceded by a negation word."""
        tokens = re.findall(r"[a-z0-9+#.]+", (evidence or "").lower())
        if not tokens:
            return False

        kw_token_lists = [
            re.findall(r"[a-z0-9+#.]+", str(kw).lower())
            for kw in (keywords or [])
            if str(kw).strip()
        ]
        if not kw_token_lists:
            return any(tok in cls._NEGATION_WORDS for tok in tokens[:4])

        matched_positions: list[int] = []
        for kw_tokens in kw_token_lists:
            if not kw_tokens:
                continue
            first_kw = kw_tokens[0]
            for idx, tok in enumerate(tokens):
                if tok == first_kw or tok.startswith(first_kw):
                    matched_positions.append(idx)

        for idx in matched_positions:
            window = tokens[max(0, idx - 4) : idx]
            if any(tok in cls._NEGATION_WORDS for tok in window):
                return True
        return False

    @staticmethod
    def _evidence_is_valid(evidence: str, keywords: list[str], matcher: TextMatcher) -> bool:
        """The quote must really be in the resume, and must mention one of the rule's keywords."""
        if not evidence or not matcher.contains(evidence):
            return False
        if keywords and not TextMatcher(evidence).has_any_word(keywords):
            return False
        return True

    def _add_exact_word_matches(self, proven: list[int], unproven: list[int], matcher: TextMatcher) -> None:
        """Credits rules whose own words or shared specific keywords are in the resume."""
        cleaned_tokens = matcher._cleaned_text.split()
        for number, rule in enumerate(self._rules, 1):
            # Knockout rules are skipped: "No criminal record" contains "criminal record".
            if rule["priority"] == self._KNOCKOUT or number in proven:
                continue
            words = rule["text"].strip()
            matched = matcher.has_any_word([words, words + "s"])
            if not matched:
                rule_tokens = {tok for tok in re.findall(r"[a-z0-9]+", words.lower()) if len(tok) >= 2}
                kw_tokens = {
                    tok
                    for kw in (rule.get("keywords") or [])
                    for tok in re.findall(r"[a-z0-9]+", str(kw).lower())
                    if len(tok) >= 2
                }
                shared = rule_tokens & kw_tokens
                specific = [tok for tok in shared if tok not in self._GENERIC_TOKENS]
                candidates = specific if specific else sorted(shared)
                if candidates and self._any_token_present_unnegated(candidates, cleaned_tokens):
                    matched = True

            if matched:
                proven.append(number)
                if number in unproven:
                    unproven.remove(number)

    @classmethod
    def _any_token_present_unnegated(cls, candidate_tokens: list[str], cleaned_tokens: list[str]) -> bool:
        """True if any candidate token appears in cleaned_tokens without a nearby negation."""
        cand_set = set(candidate_tokens)
        for idx, tok in enumerate(cleaned_tokens):
            if tok in cand_set:
                window = cleaned_tokens[max(0, idx - 4) : idx]
                if not any(w in cls._NEGATION_WORDS for w in window):
                    return True
        return False

    def _build_result(self, proven: list[int], unproven: list[int]) -> dict:
        """Adds up the points and writes the reason."""
        earned = 0
        total = 0
        met = []
        missed = []
        rejected_by = []

        for number, rule in enumerate(self._rules, 1):
            if rule["priority"] == self._KNOCKOUT:
                if number in proven:
                    rejected_by.append(rule["text"])
                continue
            weight = self._PRIORITY_WEIGHTS.get(rule["priority"], 1)
            total += weight
            if number in proven:
                earned += weight
                met.append(rule["text"])
            else:
                missed.append(rule["text"])

        score = round(earned / total * 100, 1) if total > 0 else 0.0
        reason = self._build_reason(met, missed, rejected_by, unproven)
        return {"score": score, "rejected_by": rejected_by, "reason": reason,
                "rules_met": met, "rules_missed": missed}
    
    @staticmethod
    def _build_reason(met: list[str], missed: list[str], rejected_by: list[str], unproven: list[int]) -> str:
        if rejected_by:
            reason = "Rejected: " + "; ".join(rejected_by)
        elif not missed:
            reason = "Meets all rules."
        else:
            reason = f"Meets {len(met)}/{len(met) + len(missed)} rules. Missing: " + "; ".join(missed)

        if unproven:
            reason += f" (Ignored {len(unproven)} unverified claims)."
        return reason