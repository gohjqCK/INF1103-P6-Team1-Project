"""Works out a resume's score from the AI's checks, trusting only what the resume really says."""
from ai_manager_modules.ai_manager_text_matcher import TextMatcher


class ResumeScorer:
    """Scores resumes against one set of rules. A rule counts only if it can be proven from the resume text."""

    _PRIORITY_WEIGHTS = {"must": 4, "important": 3, "nice": 2, "can consider": 1}
    _KNOCKOUT = "reject"

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
            keywords = self._rules[check["id"] - 1].get("keywords", [])
            if self._evidence_is_valid(check["evidence"], keywords, matcher):
                proven.append(check["id"])
            else:
                unproven.append(check["id"])
        return proven, unproven

    @staticmethod
    def _evidence_is_valid(evidence: str, keywords: list[str], matcher: TextMatcher) -> bool:
        """The quote must really be in the resume, and must mention one of the rule's keywords."""
        if not evidence or not matcher.contains(evidence):
            return False
        if keywords and not TextMatcher(evidence).has_any_word(keywords):
            return False
        return True

    def _add_exact_word_matches(self, proven: list[int], unproven: list[int], matcher: TextMatcher) -> None:
        """Credits rules whose own words are in the resume, because the AI sometimes misses them."""
        for number, rule in enumerate(self._rules, 1):
            # Knockout rules are skipped: "No criminal record" contains "criminal record".
            if rule["priority"] == self._KNOCKOUT or number in proven:
                continue
            words = rule["text"].strip()
            if matcher.has_any_word([words, words + "s"]):
                proven.append(number)
                if number in unproven:
                    unproven.remove(number)

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
        return {"score": score, "rejected_by": rejected_by, "reason": reason}

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