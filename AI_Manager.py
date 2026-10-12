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

from Data_Manager import EMBED_MODEL, parse_resumes, save_resumes

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
     "If it is NOT a resume, set rules_check to [] and candidate_info to null.\n"
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

KEYWORD_BATCH_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "For each rule, list 3 to 12 concise keywords (tech, tools, specific terms) that would appear in a resume matching it. "
     "Exclude generic words like experience, skills, knowledge. "
     "Reply strictly in JSON: {{\n  \"1\": [\"kw1\", \"kw2\"],\n  \"2\": [\"kw1\", \"kw2\"]\n}}"),
    ("human", "Rules:\n{rules}"),
])


def check_connection() -> bool:
    try:
        client = ollama.Client(host=OLLAMA_HOST)
        downloaded = [m.model for m in client.list().models]
    except Exception:
        print(f"Cannot reach Ollama at {OLLAMA_HOST}.")
        return False

    for model in [MODEL_NAME, EMBED_MODEL]:
        if model not in downloaded and model + ":latest" not in downloaded:
            print(f"Model '{model}' is not downloaded.")
            return False
    return True


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


def contains_text(substring: str, text: str) -> bool:
    """Fast check to see if substring exists in text (ignoring case & extra spaces)."""
    clean_sub = clean_text(substring).strip()
    if not clean_sub:
        return False
    return clean_sub in clean_text(text)


def has_keyword(text: str, keywords: list[str]) -> bool:
    """Fast exact word boundary matching for keywords."""
    cleaned_text = clean_text(text)
    for kw in keywords:
        clean_kw = clean_text(kw).strip()
        if clean_kw and re.search(rf'\b{re.escape(clean_kw)}\b', cleaned_text):
            return True
    return False


def evidence_is_valid(evidence: str, resume_text: str, keywords: list[str]) -> bool:
    if not evidence or not contains_text(evidence, resume_text):
        return False
    if keywords and not has_keyword(evidence, keywords):
        return False
    return True


# --- Batch Processing Keywords ---

def add_keywords(rules: list[dict]) -> list[dict]:
    rules_text = "\n".join(f"{i+1}. {r['text']}" for i, r in enumerate(rules))
    try:
        prompt = KEYWORD_BATCH_PROMPT.invoke({"rules": rules_text})
        suggested = json.loads(get_llm().invoke(prompt).content)
    except Exception:
        suggested = {}

    for idx, rule in enumerate(rules, 1):
        raw_kws = suggested.get(str(idx), [])
        kws = [w.strip() for w in raw_kws if w.strip().lower() not in GENERAL_WORDS]
        rule["keywords"] = list(set(kws))
        print(f"Keywords for '{rule['text']}': {', '.join(rule['keywords']) if rule['keywords'] else '(quote check only)'}")
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
        
        doc_type = result.get("document_type", "").lower()
        if doc_type != "resume":
            resume["status"] = "invalid"
            resume["reason"] = f"Not a resume ({doc_type}): {result.get('doc_type_reason', '')}"
            entry["outcome"] = "invalid"
            entry["reason"] = resume["reason"]
            return entry

        # Rules Check & Scoring
        outcome = score_resume(rules, result.get("checks", []), resume["text"])
        entry["reason"] = outcome["reason"]

        if outcome["rejected_by"]:
            entry["outcome"] = "rejected"
        else:
            entry["outcome"] = "scored"
            entry["score"] = outcome["score"]

            # Extract Info Validation
            info = result.get("candidate_info", {}) or {}
            for field in ["name", "email", "phone"]:
                val = str(info.get(field, ""))
                if contains_text(val, resume["text"]):
                    entry[field] = val

            entry["summary"] = str(info.get("summary", ""))
            
            # Categories with deduplication & skill validation
            for cat in ["qualifications", "work_experience", "projects"]:
                entry[cat] = [str(x) for x in info.get(cat, []) if isinstance(x, (str, int))]
            
            entry["skills"] = [
                str(s) for s in info.get("skills", []) 
                if isinstance(s, str) and contains_text(s, resume["text"])
            ]

    except Exception as error:
        resume["status"] = "invalid"
        resume["reason"] = f"Processing failed: {error}"
        entry["outcome"] = "invalid"
        entry["reason"] = resume["reason"]

    return entry


# --- Parallel Batch Runner ---

def screen_resumes(rules: list[dict], resumes: list[dict],
                   resumes_file: str = "resumes.json", results_file: str = "results.json", max_workers: int = 4) -> list[dict]:
    
    scored, rejected, invalid = [], [], []

    print(f"Screening {len(resumes)} resumes using up to {max_workers} threads...")
    
    # Process resumes concurrently to maximize Ollama GPU/CPU utilization
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_resume = {executor.submit(screen_one, rules, res): res for res in resumes}
        
        for future in as_completed(future_to_resume):
            entry = future.result()
            print(f"[{entry['file']}] -> {entry['outcome'].upper()}: {entry['reason']}")
            
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


if __name__ == "__main__":
    if check_connection():
        rules = [
            {"text": "At least 2 years of networking experience", "priority": "must"},
            {"text": "CCNA is listed as a certification", "priority": "important"},
            {"text": "Has cloud experience", "priority": "nice"},
            {"text": "Has a criminal record", "priority": "reject"},
        ]
        rules = add_keywords(rules)
        resumes = parse_resumes("data_test", "resumes.json")
        screen_resumes(rules, resumes, "resumes.json", "results.json", max_workers=4)