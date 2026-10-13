# AI Manager: checks, scores and summarises resumes with a local AI model (Ollama).
import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import ollama
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from Data_Manager import parse_resumes, save_resumes

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

PRIORITY_WEIGHTS = {"must": 4, "important": 3, "nice": 2, "can consider": 1}
DOCUMENT_TYPES = ["resume", "job_description", "guide_or_sample", "other"]
GENERAL_WORDS = {"experience", "years", "year", "skills", "skill", "has", "have", "knowledge",
                 "certification", "certifications", "certified", "record", "records", "related", "field", "good", "strong"}

# Combined Prompt: Analyzes document type, checks rules, and extracts key candidate info in 1 pass.
COMBINED_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are an impartial resume screening assistant. Today is {today}.\n"
     "Analyze the given document and perform three tasks:\n"
     "1. Identify document_type: 'resume', 'job_description', 'guide_or_sample', or 'other'. "
     "If it is NOT a resume, set checks to [] and candidate_info to null.\n"
     "2. If it is a resume, check it ONLY against the provided numbered rules. "
     "Do not infer or guess. For evidence, quote exact text from the resume or use \"\".\n"
     "3. Extract key details into candidate_info (ignore personal attributes like age/gender/ethnicity).\n\n"
     "Reply strictly in this JSON format:\n"
     '{{\n'
     '  "document_type": "resume|job_description|guide_or_sample|other",\n'
     '  "doc_type_reason": "<one sentence explanation>",\n'
     '  "checks": [{{"id": 1, "evidence": "<exact quote or empty>", "shows": true|false}}],\n'
     '  "candidate_info": {{\n'
     '    "name": "...", "email": "...", "phone": "...", "summary": "<2-3 sentences>",\n'
     '    "skills": ["..."], "qualifications": ["..."], "work_experience": ["..."], "projects": ["..."]\n'
     '  }}\n'
     '}}'),
    ("human", "Rules:\n{rules}\n\nDocument:\n{resume}"),
])

# Keyword Prompt: Generates a list of keywords for a given rule to help match resumes.
KEYWORD_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You help a hiring team check resumes against their rules. "
     "For the rule given, list 3 to 12 SHORT keywords (one or two words each) that a sentence from a resume "
     "would contain if it is about this rule. Include:\n"
     "- the main word and its other forms (singular, plural, -ing)\n"
     "- abbreviations and their full names\n"
     "- well-known products, tools or vendors that clearly prove the rule\n"
     "Do not include general words such as experience, years, skills, has, knowledge or certification.\n"
     'Example: for the rule "Knows relational databases" the keywords could be '
     '["database", "databases", "SQL", "MySQL", "PostgreSQL", "Oracle", "SQL Server"].\n'
     "If the rule is too general to check with specific words, give an empty list.\n"
     "Reply ONLY with JSON in exactly this format: "
     '{{"keywords": ["<keyword>", "..."]}}'),
    ("human", "Rule: {rule}"),
])

# This functions checks if the Ollama server is reachable
def check_connection() -> bool:
    try:
        client = ollama.Client(host=OLLAMA_HOST)
        downloaded = [m.model for m in client.list().models]
    except Exception:
        print(f"Cannot reach Ollama at {OLLAMA_HOST}.")
        return False

    if MODEL_NAME not in downloaded and MODEL_NAME + ":latest" not in downloaded:
        print(f"Model '{MODEL_NAME}' is not downloaded.")
        return False
    return True

# Set up a ChatOllama instance with the specified model and parameters
def get_llm() -> ChatOllama:
    return ChatOllama(
        model=MODEL_NAME,
        base_url=OLLAMA_HOST,
        temperature=0,
        format="json",
        seed=42,
        num_ctx=8192,
    )


# --- Fast Text Processing (Regex & Normalization) ---
def clean_text(text: str) -> str:
    """Normalizes Unicode ligatures, converts to lower case, and keeps alphanumeric words."""
    normalized = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r'[^a-z0-9]+', ' ', normalized)

# Checks if a substring exists in a text, ignoring case and extra spaces.
def contains_text(substring: str, text: str) -> bool:
    clean_sub = clean_text(substring).strip()
    if not clean_sub:
        return False
    return clean_sub in clean_text(text)

# checks if any of the keywords appear as whole words in the text, ignoring case and punctuation.
def has_keyword(text: str, keywords: list[str]) -> bool:
    cleaned_text = clean_text(text)
    for kw in keywords:
        clean_kw = clean_text(kw).strip()
        if clean_kw and re.search(rf'\b{re.escape(clean_kw)}\b', cleaned_text):
            return True
    return False

# Checks if the evidence is valid based on its presence in the resume and the presence of specified keywords.
def evidence_is_valid(evidence: str, resume_text: str, keywords: list[str]) -> bool:
    if not evidence or not contains_text(evidence, resume_text):
        return False
    if keywords and not has_keyword(evidence, keywords):
        return False
    return True

# Checks if the rule's own words appear in the resume
def rule_text_in_resume(rule_text: str, resume_text: str) -> bool:
    words = rule_text.strip()
    return has_keyword(resume_text, [words, words + "s"])


# --- Rule Keywords ---
def add_keywords(rules: list[dict]) -> list[dict]:
    # Ask the AI for keywords for each rule (one small call per rule), clean them, and add other word forms.
    for rule in rules:
        # 1. Ask the AI for this rule's keywords
        try:
            prompt = KEYWORD_PROMPT.invoke({"rule": rule["text"]})
            suggested = json.loads(get_llm().invoke(prompt).content).get("keywords", [])
        except Exception:
            suggested = []      # no keywords: this rule falls back to the quote check only
        if not isinstance(suggested, list):
            suggested = []

        # 2. Clean the list: keep a keyword only if it has a useful word (not just "2 years")
        keywords = []
        for word in suggested:
            word = str(word).strip()
            useful = []
            for part in word.lower().split():
                if not part.isdigit() and part not in GENERAL_WORDS:
                    useful.append(part)
            if len(useful) > 0 and word not in keywords:
                keywords.append(word)

        # 3. Add other forms of lower-case single words, e.g. "networking" -> "network", "networks"
        forms = []
        for word in keywords:
            if word.islower() and " " not in word and len(word) >= 4:
                if word.endswith("ing"):
                    forms.append(word[:-3])
                    forms.append(word[:-3] + "s")
                elif word.endswith("s"):
                    forms.append(word[:-1])
                else:
                    forms.append(word + "s")
        for form in forms:
            if form not in keywords:
                keywords.append(form)

        # 4. Save the keywords on the rule and show them
        rule["keywords"] = keywords
        if len(keywords) > 0:
            print(f"Keywords for '{rule['text']}': " + ", ".join(keywords))
        else:
            print(f"Keywords for '{rule['text']}': (quote check only)")

    return rules


# --- Single-Pass Resume Screening ---
def score_resume(rules: list[dict], checks: list[dict], resume_text: str) -> dict:
    shown, unproven = [], []
    for check in checks:
        rule_id = int(check.get("id", 0))
        evidence = str(check.get("evidence", ""))
        if check.get("shows"):
            kws = rules[rule_id - 1].get("keywords", []) if 1 <= rule_id <= len(rules) else []
            if evidence_is_valid(evidence, resume_text, kws):
                shown.append(rule_id)
            else:
                unproven.append(rule_id)

    # Exact-words check: the AI sometimes says "no" even when the skill is written in the resume.
    # Knockout ("reject") rules are skipped: "No criminal record" contains "criminal record".
    for idx, rule in enumerate(rules, 1):
        if rule["priority"] == "reject":
            continue
        if idx in shown:
            continue
        if rule_text_in_resume(rule["text"], resume_text):
            shown.append(idx)
            if idx in unproven:
                unproven.remove(idx)

    earned, total, musts_missed = 0, 0, 0
    met, missed, rejected_by = [], [], []

    for idx, rule in enumerate(rules, 1):
        priority = rule["priority"]
        if priority == "reject":
            if idx in shown:
                rejected_by.append(rule["text"])
        else:
            weight = PRIORITY_WEIGHTS.get(priority, 1)
            total += weight
            if idx in shown:
                earned += weight
                met.append(rule["text"])
            else:
                missed.append(rule["text"])
                if priority == "must":
                    musts_missed += 1

    score = round(earned / total * 100, 1) if total > 0 else 0.0

    if rejected_by:
        reason = "Rejected: " + "; ".join(rejected_by)
    elif not missed:
        reason = "Meets all rules."
    else:
        reason = f"Meets {len(met)}/{len(met)+len(missed)} rules. Missing: " + "; ".join(missed)

    if unproven:
        reason += f" (Ignored {len(unproven)} unverified claims)."

    return {"score": score, "rejected_by": rejected_by, "musts_missed": musts_missed, "reason": reason}

# Screens a single resume against the rules and returns the result as a dictionary.
def screen_one(rules: list[dict], resume: dict) -> dict:
    entry = {"file": resume["file"], "name": "", "email": "", "phone": "",
             "outcome": "", "score": None, "reason": "",
             "summary": "", "skills": [], "qualifications": [], "work_experience": [], "projects": []}

    if resume.get("status") == "invalid":
        entry["outcome"] = "invalid"
        entry["reason"] = resume["reason"]
        return entry

    rules_text = "\n".join(f"{i+1}. {r['text']}" for i, r in enumerate(rules))
    today = date.today().strftime("%d %B %Y")

    try:
        prompt = COMBINED_PROMPT.invoke({"today": today, "rules": rules_text, "resume": resume["text"]})
        result = json.loads(get_llm().invoke(prompt).content)
        
        # "or" swaps a missing / null value for a safe default, so null never crashes the program
        doc_type = str(result.get("document_type") or "unknown").lower()
        if doc_type != "resume":
            resume["status"] = "invalid"
            resume["reason"] = f"Not a resume ({doc_type}): {result.get('doc_type_reason') or ''}"
            entry["outcome"] = "invalid"
            entry["reason"] = resume["reason"]
            return entry

        # Rules Check & Scoring (no checks at all means the AI skipped the rules, so the score can't be trusted)
        checks = result.get("checks")
        if not isinstance(checks, list):
            resume["status"] = "invalid"
            resume["reason"] = "The AI's reply did not include the rule checks."
            entry["outcome"] = "invalid"
            entry["reason"] = resume["reason"]
            return entry

        outcome = score_resume(rules, checks, resume["text"])
        entry["reason"] = outcome["reason"]

        if outcome["rejected_by"]:
            entry["outcome"] = "rejected"
        else:
            entry["outcome"] = "scored"
            entry["score"] = outcome["score"]

            # Extract Info Validation
            info = result.get("candidate_info") or {}
            if not isinstance(info, dict):
                info = {}

            for field in ["name", "email", "phone"]:
                val = str(info.get(field) or "")      # null becomes "" (not the text "None")
                if contains_text(val, resume["text"]):
                    entry[field] = val

            entry["summary"] = str(info.get("summary") or "")

            # Categories: a null or non-list value becomes an empty list instead of crashing
            for cat in ["qualifications", "work_experience", "projects", "skills"]:
                items = info.get(cat) or []
                if not isinstance(items, list):
                    items = []
                if cat == "skills":
                    # Only keep skills that really appear in the resume
                    entry[cat] = [str(s) for s in items if isinstance(s, str) and contains_text(s, resume["text"])]
                else:
                    entry[cat] = [str(x) for x in items if isinstance(x, (str, int))]

    except Exception as error:
        resume["status"] = "invalid"
        resume["reason"] = f"Processing failed: {error}"
        entry["outcome"] = "invalid"
        entry["reason"] = resume["reason"]

    return entry


# --- Parallel Batch Runner ---
def screen_resumes(rules: list[dict], resumes: list[dict],
                   resumes_file: str = "resumes.json", results_file: str = "ai_output.json", max_workers: int = 4) -> list[dict]:
    
    scored, rejected, invalid = [], [], []

    print(f"Screening {len(resumes)} resumes using up to {max_workers} threads...")
    
    # Process resumes concurrently to maximize Ollama GPU/CPU utilization
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_resume = {executor.submit(screen_one, rules, res): res for res in resumes}
        
        for future in as_completed(future_to_resume):
            entry = future.result()
            print(f"[{entry['file']}] -> Scored:{entry['score']}. Reason: {entry['reason']}")
            
            if entry["outcome"] == "scored":
                scored.append(entry)
            elif entry["outcome"] == "rejected":
                rejected.append(entry)
            else:
                invalid.append(entry)

    results = scored + rejected + invalid
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    save_resumes(resumes, resumes_file)
    return results

# =====================================================================
# LOCAL STANDALONE TEST
# =====================================================================
if __name__ == "__main__":
    if check_connection():
        rules = [
            {"text": "At least 2 years of networking experience", "priority": "must"},
            {"text": "CCNA is listed as a certification", "priority": "important"},
            {"text": "Has cloud experience", "priority": "nice"},
            {"text": "Has a criminal record", "priority": "reject"},
        ]
        rules = add_keywords(rules)
        resumes = parse_resumes("data", "resumes.json")
        screen_resumes(rules, resumes, "resumes.json", "ai_output.json", max_workers=4)