"""AI Manager: checks, scores and summarises resumes with a local AI model (Ollama)."""
import json
import os
import unicodedata
from datetime import date

import ollama
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from Data_Manager import EMBED_MODEL, parse_resumes, save_resumes

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

PRIORITY_WEIGHTS = {"must": 4, "important": 3, "nice": 2, "can consider": 1}
DOCUMENT_CHECK_LENGTH = 2000   # only the first part of a document is needed to tell what it is
DOCUMENT_TYPES = ["resume", "job_description", "guide_or_sample", "other"]
NOT_RESUME_TYPES = ["job_description", "guide_or_sample", "other"]
INFO_CATEGORIES = ["qualifications", "work_experience", "projects", "skills"]   # earlier in the list wins a repeat
GENERAL_WORDS = ["experience", "years", "year", "skills", "skill", "has", "have", "knowledge",
                 "certification", "certifications", "certified",
                 "record", "records", "related", "field", "good", "strong"]   # too general to prove anything


# ---------------------------------------------------------------- Prompts

RESUME_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are an impartial resume screening assistant. Today is {today}. "
     "Check the resume ONLY against the numbered items given. "
     "Ignore name, gender, age, ethnicity, religion, nationality and any other "
     "personal details that are not related to the job.\n"
     "For each item, first copy the exact words from the resume that prove it as evidence. "
     "If no words in the resume directly prove the item, the evidence is \"\" and shows is false. "
     "Do not guess or infer: a related skill is not the same as a certification or qualification. "
     "When an item needs years of experience, work them out from the dates in the resume; "
     "\"Present\" means today.\n"
     "Reply ONLY with JSON in exactly this format, with one entry per item:\n"
     '{{"checks": [{{"id": <item number>, "evidence": "<exact quote from the resume, or empty>", "shows": true or false}}]}}'),
    ("human",
     "Items to check:\n{rules}\n\n"
     "Resume:\n{resume}"),
])

DOCUMENT_TYPE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You sort documents for a hiring team. Decide what kind of document this is.\n"
     '"resume" = one person\'s own CV or resume.\n'
     '"job_description" = an employer describing a job and its requirements.\n'
     '"guide_or_sample" = advice about writing resumes, a template pack, or a before-and-after example.\n'
     '"other" = anything else.\n'
     "Reply ONLY with JSON in exactly this format:\n"
     '{{"type": "resume" or "job_description" or "guide_or_sample" or "other", '
     '"reason": "<one short sentence>"}}'),
    ("human",
     "Document (first part only):\n{text}"),
])

EXTRACT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You pull key information out of a resume for a hiring team. "
     "The resume text was copied from a PDF, so some lines may be out of order; read all of it.\n"
     "Put each piece of information into exactly ONE category:\n"
     '"name": the candidate\'s full name, copied exactly from the resume, or "" if it is not given.\n'
     '"email": their email address, copied exactly, or "".\n'
     '"phone": their phone number, copied exactly, or "".\n'
     '"summary": 2-3 sentences you write about the candidate\'s main role, years of experience and focus. '
     "Do not mention their name, age, gender, nationality or other personal details.\n"
     '"skills": short names of technical skills, tools, technologies, programming languages and methods, '
     "copied exactly as the resume writes them. Not certifications, degrees, job titles or full sentences.\n"
     '"qualifications": every degree, diploma, certification, licence and training course, '
     'as "<qualification>, <institution>, <year>" (leave out any part the resume does not give).\n'
     '"work_experience": one entry per job as "<job title>, <company>, <dates>".\n'
     '"projects": one entry per project the resume names, as "<project name>: <one short sentence>". '
     "Normal job duties are not projects.\n"
     "Only use information written in the resume; do not invent anything. "
     "If a category has nothing, give an empty list. "
     "Never put the same item in two categories: a certification is a qualification, not a skill.\n"
     "Reply ONLY with JSON in exactly this format:\n"
     '{{"name": "...", "email": "...", "phone": "...", "summary": "<2-3 sentences>", "skills": ["..."], '
     '"qualifications": ["..."], "work_experience": ["..."], "projects": ["..."]}}'),
    ("human",
     "Resume:\n{resume}"),
])

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
    ("human",
     "Rule: {rule}"),
])


# ---------------------------------------------------------------- Connection

def check_connection() -> bool:
    """Check that the Ollama server is reachable and both models (AI + embeddings) are downloaded."""
    try:
        client = ollama.Client(host=OLLAMA_HOST)
        models = client.list().models
    except ConnectionError:
        print(f"Cannot reach Ollama at {OLLAMA_HOST}. Is it running? (docker compose up -d)")
        return False

    # Downloaded names look like "qwen2.5:7b" or "nomic-embed-text:latest"
    downloaded = []
    for model in models:
        downloaded.append(model.model)

    ready = True
    for needed in [MODEL_NAME, EMBED_MODEL]:
        if needed not in downloaded and needed + ":latest" not in downloaded:
            print(f"Model '{needed}' is not downloaded. Download it with: "
                  f"docker compose exec ollama ollama pull {needed}")
            ready = False

    if ready:
        print(f"Connected to {OLLAMA_HOST}. Using '{MODEL_NAME}' and '{EMBED_MODEL}'.")
    return ready


def get_llm() -> ChatOllama:
    """Create the connection to the AI model on the Ollama server."""
    return ChatOllama(
        model=MODEL_NAME,       # which model to use
        base_url=OLLAMA_HOST,   # where the Ollama server is
        temperature=0,          # straightforward answers, no randomness
        format="json",          # force the model to reply with valid JSON
        seed=42,                # fixed randomness so the same input gives the same output
        num_ctx=8192,           # how many tokens the model can read at once
    )


# ---------------------------------------------------------------- Text checks (plain Python, no AI)

def found_in_text(item: str, text: str) -> bool:
    """Check if an item appears in the text, ignoring capital letters, spaces, line breaks and ligatures."""
    # Turn special PDF characters like "ﬂ" into normal letters like "fl"
    item = unicodedata.normalize("NFKC", item)
    text = unicodedata.normalize("NFKC", text)

    item_squashed = ""
    for ch in item.lower():
        if not ch.isspace():
            item_squashed += ch

    text_squashed = ""
    for ch in text.lower():
        if not ch.isspace():
            text_squashed += ch

    return item_squashed in text_squashed


def to_words(text: str) -> str:
    """Lower-case the text and turn every symbol into a space, so only words and numbers are left."""
    cleaned = ""
    for ch in unicodedata.normalize("NFKC", text).lower():
        if ch.isalnum():
            cleaned += ch
        else:
            cleaned += " "
    return " " + " ".join(cleaned.split()) + " "     # e.g. "AWS (Lambda)" -> " aws lambda "


def has_keyword(text: str, keywords: list[str]) -> bool:
    """Check if any keyword appears in the text as a whole word, e.g. "cloud" matches "cloud", not "Cloudlet"."""
    words = to_words(text)
    for keyword in keywords:
        if to_words(keyword) in words:
            return True
    return False


def evidence_is_valid(evidence: str, resume_text: str, keywords: list[str]) -> bool:
    """Evidence counts only if it is not empty, really is in the resume, and has a keyword (when the rule has keywords)."""
    if evidence == "":
        return False                  # no quote at all
    elif not found_in_text(evidence, resume_text):
        return False                  # the quote is not really in the resume
    elif len(keywords) > 0 and not has_keyword(evidence, keywords):
        return False                  # the quote is real but does not mention what the rule is about
    else:
        return True


# ---------------------------------------------------------------- Rule keywords

def suggest_keywords(rule_text: str) -> list[str]:
    """Ask the AI for keywords that evidence for this rule should contain. Returns [] if it can't suggest any."""
    # 1. Ask the AI for keywords
    try:
        prompt = KEYWORD_PROMPT.invoke({"rule": rule_text})
        reply = get_llm().invoke(prompt)
        suggested = json.loads(reply.content).get("keywords", [])
    except Exception:
        suggested = []      # no keywords: the rule will only use the quote check

    # 2. Clean the list: text only, no general words, no repeats
    keywords = []
    for word in suggested:
        word = str(word).strip()
        if word != "" and word.lower() not in GENERAL_WORDS and word not in keywords:
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

    return keywords


def add_keywords(rules: list[dict]) -> list[dict]:
    """Ask the AI to suggest keywords for every rule and attach them to the rule. The user is not asked."""
    for rule in rules:
        rule["keywords"] = suggest_keywords(rule["text"])
        if len(rule["keywords"]) > 0:
            print(f"Keywords for '{rule['text']}': " + ", ".join(rule["keywords"]))
        else:
            print(f"Keywords for '{rule['text']}': (none - quote check only)")
    return rules


# ---------------------------------------------------------------- AI steps for one resume

def check_document_type(text: str) -> dict:
    """Ask the AI what kind of document this is, using only its first part."""
    # 1. Only send the beginning of the document
    prompt = DOCUMENT_TYPE_PROMPT.invoke({"text": text[:DOCUMENT_CHECK_LENGTH]})

    # 2. Send it to the AI and turn the JSON reply into a dictionary
    try:
        result = json.loads(get_llm().invoke(prompt).content)
        doc_type = str(result.get("type", "")).lower()
        reason = str(result.get("reason", ""))
    except Exception as error:
        doc_type = "unknown"
        reason = f"The check could not be completed: {error}"

    # 3. Only accept the four types we asked for
    if doc_type not in DOCUMENT_TYPES and doc_type != "unknown":
        reason = f"The AI gave an unexpected type '{doc_type}'. {reason}"
        doc_type = "unknown"

    return {"type": doc_type, "reason": reason}


def start_chat(rules: list[dict], resume_text: str) -> dict:
    """Send one resume and the rules to the AI and return its checks as a dict."""
    # 1. Turn the rules into a numbered list of text (only the text: priorities and keywords stay in Python)
    rules_text = ""
    number = 1
    for rule in rules:
        rules_text += f"{number}. {rule['text']}\n"
        number += 1

    # 2. Fill in the blanks in the prompt template, including today's date
    today = date.today().strftime("%d %B %Y")      # e.g. "08 October 2026"
    prompt = RESUME_PROMPT.invoke({"today": today, "rules": rules_text, "resume": resume_text})

    # 3. Send the prompt to the AI and convert the JSON reply into a dictionary
    reply = get_llm().invoke(prompt)
    return json.loads(reply.content)


def score_resume(rules: list[dict], result: dict, resume_text: str) -> dict:
    """Turn the AI's checks into a weighted score out of 100, counting only evidence that passes the checks."""
    # 1. Make a list of the rule numbers that are proven: the AI says yes AND the evidence passes our checks
    shown = []
    unproven = []
    for check in result["checks"]:
        evidence = str(check.get("evidence", ""))
        rule_id = int(check["id"])
        if check.get("shows") == True:
            keywords = []
            if 1 <= rule_id <= len(rules):
                keywords = rules[rule_id - 1].get("keywords", [])
            if evidence_is_valid(evidence, resume_text, keywords):
                shown.append(rule_id)
            else:
                unproven.append(rule_id)      # the AI said yes, but its evidence did not pass

    # 2. Go through the rules in the same order start_chat() numbered them
    earned = 0
    total = 0
    musts_missed = 0
    met = []
    missed = []
    rejected_by = []
    number = 1
    for rule in rules:
        priority = rule["priority"]

        if priority == "reject":
            # A reject rule gives no points; it only knocks the applicant out
            if number in shown:
                rejected_by.append(rule["text"])
        else:
            # Every other rule adds its weight to the total possible points
            weight = PRIORITY_WEIGHTS[priority]
            total += weight
            if number in shown:
                earned += weight
                met.append(rule["text"])
            else:
                missed.append(rule["text"])
                if priority == "must":
                    musts_missed += 1

        number += 1

    # 3. Score = share of the possible points that were earned
    if total > 0:
        score = round(earned / total * 100, 1)
    else:
        score = 0.0     # every rule was a reject rule, so there is nothing to score

    # 4. Explain the result in plain words
    if len(rejected_by) > 0:
        reason = "Rejected because the resume shows: " + "; ".join(rejected_by)
    elif len(missed) == 0:
        reason = "Meets every rule."
    else:
        reason = f"Meets {len(met)} of {len(met) + len(missed)} rules. Missing: " + "; ".join(missed)

    if len(unproven) > 0:
        reason += f" (Ignored {len(unproven)} claim(s) whose evidence did not pass the checks.)"

    return {"score": score, "rejected_by": rejected_by, "musts_missed": musts_missed, "reason": reason}


def remove_repeats(info: dict) -> dict:
    """Keep each item in only one category: the first category (in INFO_CATEGORIES order) it appears in."""
    seen = []
    for category in INFO_CATEGORIES:
        unique = []
        for item in info[category]:
            key = item.strip().lower()
            if key not in seen:
                seen.append(key)
                unique.append(item)
        info[category] = unique
    return info


def extract_key_info(resume_text: str) -> dict:
    """Ask the AI for the contact details and key information, sorted into categories with no repeats."""
    info = {"name": "", "email": "", "phone": "", "summary": "",
            "skills": [], "qualifications": [], "work_experience": [], "projects": []}

    # 1. Fill in the prompt and send it to the AI
    try:
        prompt = EXTRACT_PROMPT.invoke({"resume": resume_text})
        result = json.loads(get_llm().invoke(prompt).content)
    except Exception as error:
        info["summary"] = f"Key information could not be extracted: {error}"
        return info

    # 2. Copy the contact details, but only if they really appear in the resume
    for field in ["name", "email", "phone"]:
        value = str(result.get(field, ""))
        if found_in_text(value, resume_text):
            info[field] = value

    # 3. Copy the summary and each category, making sure lists really are lists of text
    info["summary"] = str(result.get("summary", ""))
    for category in INFO_CATEGORIES:
        items = result.get(category, [])
        if isinstance(items, list):
            for item in items:
                info[category].append(str(item))

    # 4. Only keep skills that really appear in the resume (the AI sometimes invents them)
    real_skills = []
    for skill in info["skills"]:
        if found_in_text(skill, resume_text):
            real_skills.append(skill)
    info["skills"] = real_skills

    # 5. Remove anything the AI put in more than one category
    return remove_repeats(info)


# ---------------------------------------------------------------- Screening

def screen_one(rules: list[dict], resume: dict) -> dict:
    """Check, score and summarise one resume. Also marks the resume invalid if the AI says it isn't one."""
    entry = {"file": resume["file"], "name": "", "email": "", "phone": "",
             "outcome": "", "score": None, "reason": "",
             "summary": "", "skills": [], "qualifications": [], "work_experience": [], "projects": []}

    if resume["status"] == "invalid":
        # 1. Already invalid when the PDF was read
        entry["outcome"] = "invalid"
        entry["reason"] = resume["reason"]
    else:
        # 2. Ask the AI whether this is really a resume
        document = check_document_type(resume["text"])
        if document["type"] in NOT_RESUME_TYPES:
            resume["status"] = "invalid"
            resume["reason"] = f"Not a resume ({document['type']}): {document['reason']}"
            entry["outcome"] = "invalid"
            entry["reason"] = resume["reason"]
        else:
            # 3. Check the rules and score them
            try:
                result = start_chat(rules, resume["text"])
                outcome = score_resume(rules, result, resume["text"])
            except Exception as error:
                outcome = None
                resume["status"] = "invalid"
                resume["reason"] = f"The AI's reply could not be used: {error}"
                entry["outcome"] = "invalid"
                entry["reason"] = resume["reason"]

            # 4. Rejected applicants stop here; everyone else gets their key information pulled out
            if outcome is not None:
                entry["reason"] = outcome["reason"]
                if len(outcome["rejected_by"]) > 0:
                    entry["outcome"] = "rejected"
                else:
                    entry["outcome"] = "scored"
                    entry["score"] = outcome["score"]
                    info = extract_key_info(resume["text"])
                    for field in info:
                        entry[field] = info[field]

    return entry


def screen_resumes(rules: list[dict], resumes: list[dict],
                   resumes_file: str = "resumes.json", results_file: str = "results.json") -> list[dict]:
    """Screen every resume, then save results.json (scored, rejected, invalid) and update resumes.json."""
    scored = []
    rejected = []
    invalid = []

    # 1. Screen the resumes one by one and sort each result into its list
    count = 1
    for resume in resumes:
        print(f"[{count}/{len(resumes)}] {resume['file']}")
        entry = screen_one(rules, resume)
        print(f"    {entry['outcome']}: {entry['reason']}")
        if entry["outcome"] == "scored":
            scored.append(entry)
            print(f"    Score: {entry['score']}/100")
        elif entry["outcome"] == "rejected":
            rejected.append(entry)
        else:
            invalid.append(entry)
        count += 1

    # 2. Save the results: scored first, then rejected, invalid at the bottom
    results = scored + rejected + invalid
    with open(results_file, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=2, ensure_ascii=False)

    # 3. Save resumes.json again, because some resumes may now be marked invalid
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
        # For a quick test, use the "test_data" folder and "test_resumes.json" / "test_results.json" instead
        resumes = parse_resumes("data", "resumes.json")
        screen_resumes(rules, resumes, "resumes.json", "results.json")