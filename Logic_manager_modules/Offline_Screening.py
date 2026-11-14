"""Offline screening: scores resumes without the AI.

Used when the AI is unavailable. It follows the same rules as the AI scorer:
priority weights, knockout ("reject") rules, and a score out of 100.
Logic_Manager re-exports offline_screening_func, so existing callers keep working.
"""
import math
import re
import unicodedata

_PRIORITY_WEIGHTS = {"must": 4, "important": 3, "nice": 2, "can consider": 1}
_KNOCKOUT_PRIORITY = "reject"
_PARTIAL_COVERAGE = 0.6  # share of a rule's key terms that must appear for a rule with 3+ terms to count

_NEGATIONS = {"no", "not", "without", "never", "none", "free"}
_LEADING_NEGATIONS = {"no", "not", "without", "never", "has", "have", "having", "with", "any"}

# Words that say nothing about fit: they sit in most rules and in most resumes
_FILLER_WORDS = {
    "the", "and", "for", "with", "has", "have", "having", "are", "was", "were", "from", "that", "this",
    "their", "into", "able", "can", "will", "must", "should", "may", "any", "all", "per", "via", "our",
    "you", "your", "its", "than", "then", "also", "such", "etc", "an", "to", "of", "in", "on", "at",
    "by", "as", "is", "or", "if", "it", "we", "be", "do", "no", "not", "without", "never", "none",
    "skill", "skills", "experience", "experiences", "experienced", "knowledge", "knowledgeable",
    "strong", "good", "great", "excellent", "proven", "solid", "proficient", "proficiency",
    "familiarity", "familiar", "understanding", "working", "work", "years", "year", "yrs", "yr",
    "minimum", "least", "preferred", "required", "relevant", "demonstrated", "background",
    "expertise", "using", "use", "plus", "bonus",
}

# Words that mean a line is a heading or job title rather than a person's name
_NOT_A_NAME = {
    "resume", "curriculum", "vitae", "cv", "profile", "summary", "objective", "contact", "education",
    "experience", "skills", "projects", "references", "personal", "details", "information", "page",
    "name", "email", "phone", "address", "about", "me", "work", "history", "professional", "career",
    "developer", "engineer", "manager", "analyst", "designer", "intern", "consultant", "specialist",
    "officer", "assistant", "executive", "administrator", "technician", "programmer", "architect",
    "scientist", "student", "graduate",
}

_YEARS_PATTERN = re.compile(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b")
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_PATTERN = re.compile(r"(?<!\d)[+(]?\d[\d\s().\-]{6,}\d(?!\d)")
_YEAR_RANGE_PATTERN = re.compile(r"(19|20)\d{2}\s*[-–]\s*(19|20)\d{2}")


def _clean_words(text):
    '''Lowercases, fixes PDF characters, and splits into plain words (punctuation becomes a space)'''
    normalized = unicodedata.normalize("NFKC", str(text or "")).lower()
    return re.sub(r"[^a-z0-9]+", " ", normalized).split()


def _stem(word):
    '''Cuts a word down so "networks", "networking" and "networked" all match'''
    if word.isdigit():
        return word
    if word.endswith("ies") and len(word) > 4:
        word = word[:-3] + "y"
    elif word.endswith("ing") and len(word) > 5:
        word = word[:-3]
    elif word.endswith("ed") and len(word) > 4:
        word = word[:-2]
    elif word.endswith("es") and len(word) > 4:
        word = word[:-2]
    elif word.endswith("s") and len(word) > 3 and not word.endswith(("ss", "us", "is")):
        word = word[:-1]
    if len(word) > 3 and word.endswith("e"):
        word = word[:-1]
    return word


def _find_phrase(tokens, phrase):
    '''Positions where the whole phrase appears in the resume words, in order'''
    if not phrase or len(phrase) > len(tokens):
        return []
    size = len(phrase)
    return [i for i in range(len(tokens) - size + 1) if tokens[i:i + size] == phrase]


def _max_years_claimed(text):
    '''Largest "N years" figure the resume states (0 if none)'''
    found = [int(n) for n in _YEARS_PATTERN.findall(text.lower())]
    return max(found) if found else 0


def _evaluate_rule(rule, tokens, stems, max_years):
    '''Checks one normal rule against one resume: status is met, partial or missed'''
    text = str(rule.get("text", ""))
    years_needed = None
    years_match = _YEARS_PATTERN.search(text.lower())
    if years_match:
        years_needed = int(years_match.group(1))
        text = _YEARS_PATTERN.sub(" ", text.lower())

    words = _clean_words(text)
    terms = []
    for word in words:
        if (word.isdigit() or (len(word) >= 2 and word not in _FILLER_WORDS)) and word not in terms:
            terms.append(word)
    if not terms and years_needed is None:
        terms = list(dict.fromkeys(words))  # a rule made only of filler words: use its own words

    phrase_hit = _find_phrase(tokens, words) != []
    keyword_hits = [k for k in (rule.get("keywords") or []) if _find_phrase(tokens, _clean_words(k))]
    matched = [t for t in terms if _stem(t) in stems]

    needed = len(terms) if len(terms) <= 2 else math.ceil(_PARTIAL_COVERAGE * len(terms))
    terms_ok = (
        phrase_hit
        or bool(keyword_hits)
        or (len(terms) > 0 and len(matched) >= needed)
        or (not terms and years_needed is not None)
    )
    years_ok = years_needed is None or max_years >= years_needed
    met = terms_ok and years_ok

    if met:
        status = "met"
    elif matched or (terms_ok and not years_ok):
        status = "partial"
    else:
        status = "missed"

    detail = {"matched_terms": matched or keyword_hits}
    if years_needed is not None:
        detail["years_required"] = years_needed
        detail["years_found"] = max_years
    return status, detail


def _knockout_hit(rule, tokens):
    '''A knockout rule fires only on its exact wording, and not when the resume negates it ("no criminal record")'''
    words = _clean_words(rule.get("text", ""))
    while words and words[0] in _LEADING_NEGATIONS:  # "No criminal record" -> "criminal record"
        words = words[1:]
    phrases = [words] + [_clean_words(k) for k in (rule.get("keywords") or [])]
    for phrase in phrases:
        for start in _find_phrase(tokens, phrase):
            if not any(t in _NEGATIONS for t in tokens[max(0, start - 3):start]):
                return True
    return False


def _find_email(text):
    match = _EMAIL_PATTERN.search(text)
    return match.group(0) if match else ""


def _find_phone(text):
    for match in _PHONE_PATTERN.finditer(text):
        candidate = match.group(0).strip()
        digits = re.sub(r"\D", "", candidate)
        if 8 <= len(digits) <= 15 and not _YEAR_RANGE_PATTERN.fullmatch(candidate):
            return candidate
    return ""


def _guess_name(text):
    '''Takes the first short, letters-only line near the top that is not a heading or job title'''
    for line in text.splitlines()[:8]:
        line = line.strip()
        words = line.split()
        if not 2 <= len(words) <= 4 or len(line) > 40:
            continue
        if any(not re.fullmatch(r"[A-Za-z][A-Za-z.'\-]*", w) for w in words):
            continue
        if any(w.lower().strip(".") in _NOT_A_NAME for w in words):
            continue
        return " ".join(w.capitalize() if w.isupper() else w for w in words)
    return ""


def offline_screening_func(resume_list, rules):
    rules = [r for r in rules if str(r.get("text", "")).strip()]

    for resume in resume_list:
        text = str(resume.get("text") or "")
        tokens = _clean_words(text)
        if not tokens:
            resume["outcome"] = "invalid"
            resume["score"] = None
            resume["reason"] = resume.get("reason") or "No readable text"
            continue

        stems = {_stem(t) for t in tokens}
        max_years = _max_years_claimed(text)
        earned = 0
        total = 0
        met, missed, partial, rejected_by, details = [], [], [], [], []

        for rule in rules:
            rule_text = str(rule["text"]).strip()
            priority = str(rule.get("priority", "")).strip().lower()

            if priority == _KNOCKOUT_PRIORITY:
                hit = _knockout_hit(rule, tokens)
                if hit:
                    rejected_by.append(rule_text)
                details.append({"rule": rule_text, "priority": priority,
                                "status": "rejected" if hit else "clear", "matched_terms": []})
                continue

            weight = _PRIORITY_WEIGHTS.get(priority, 1)
            status, detail = _evaluate_rule(rule, tokens, stems, max_years)
            total += weight
            if status == "met":
                earned += weight
                met.append(rule_text)
            else:
                missed.append(rule_text)
                if status == "partial":
                    partial.append(rule_text)
            details.append({"rule": rule_text, "priority": priority, "weight": weight, "status": status, **detail})

        if rejected_by:
            resume["outcome"] = "rejected"
            resume["score"] = None
            reason = "Rejected: " + "; ".join(rejected_by)
        else:
            resume["outcome"] = "scored"
            resume["score"] = round(earned / total * 100, 1) if total > 0 else 0.0
            if not missed:
                reason = "Meets all rules."
            else:
                reason = f"Meets {len(met)}/{len(met) + len(missed)} rules. Missing: " + "; ".join(missed) + "."
        if partial:
            reason += " Partial match: " + "; ".join(partial) + "."

        resume["reason"] = reason
        resume["rules_met"] = met
        resume["rules_missed"] = missed
        resume["rules_partial"] = partial
        resume["rejected_by"] = rejected_by
        resume["rule_details"] = details
        resume.setdefault("name", _guess_name(text))
        resume.setdefault("email", _find_email(text))
        resume.setdefault("phone", _find_phone(text))
        if not resume.get("summary"):
            if rejected_by:
                fallback_summary = "Disqualified by knockout rule: " + "; ".join(rejected_by) + "."
            elif met:
                fallback_summary = (
                    f"Offline screening matched {len(met)}/{len(met) + len(missed)} rule(s): "
                    + ", ".join(met)
                    + "."
                )
            else:
                snippet = " ".join(line.strip() for line in text.splitlines()[:3] if line.strip())
                fallback_summary = snippet[:220] or "Evaluated via offline keyword matching."
            resume["summary"] = fallback_summary
        resume.setdefault("skills", list(met))
        resume.setdefault("qualifications", [])
        resume.setdefault("work_experience", [])
        resume.setdefault("projects", [])
    return resume_list