import json
import os
import logging
from pathlib import Path

import ollama
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_chroma import Chroma
from pypdf import PdfReader

logging.getLogger("pypdf").setLevel(logging.ERROR)   # hide pypdf's font warnings


OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "mistral")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

PRIORITY_WEIGHTS = {"must": 4, "important": 3, "nice": 2, "can consider": 1}
MIN_TEXT_LENGTH = 200     # less text than this usually means a scanned image, not a real text PDF
MAX_TEXT_LENGTH = 20000   # more than this won't fit in Mistral's context window with the prompt

HEADING_MATCH_THRESHOLD = 0.70   # below this, the heading is not similar enough to any section
SECTION_DESCRIPTIONS = {
    "contact":         "Contact details: phone number, email, address and website",
    "summary":         "Summary: a short profile or overview of the candidate and their career objective",
    "skills":          "Skills: technical skills, tools, technologies and core competencies",
    "qualifications":  "Qualifications: degrees, university, college, academic qualifications, professional certificates, licences and training courses",
    "work_experience": "Work experience: employment history, jobs held, roles and companies worked for",
    "projects":        "Projects: personal, academic or professional projects",
    "other":           "Other: awards, languages, interests, volunteering and references",
}

SECTION_HEADINGS = {
    "contact":         ["contact"],
    "summary":         ["summary", "profile", "objective", "synopsis", "highlights", "keyqualifications",
                        "aboutme", "experiencesummary"],
    "skills":          ["skills", "competencies", "expertise", "strengths", "proficiencies",
                        "technicalsummary", "highlightsofexpertise"],
    "qualifications":  ["education", "qualifications", "coursework", "academic",
                        "certification", "certificate", "credentials", "licenses", "training"],
    "work_experience": ["experience", "employment", "workhistory", "careerhistory", "careerhighlights"],
    "projects":        ["projects"],
    "other":           ["personalinformation", "awards", "languages", "interests",
                        "volunteer", "references", "affiliations", "activities"],
}

def build_section_store() -> Chroma:
    """Store each section description in ChromaDB so headings can be matched against them."""
    # 1. The embedding model that turns text into vectors
    embedder = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_HOST)

    # 2. An empty collection in memory, comparing vectors by cosine similarity
    store = Chroma(
        collection_name="section_headings",
        embedding_function=embedder,
        collection_metadata={"hnsw:space": "cosine"},
    )

    # 3. Build three matching lists: description text, its section name, and a unique id
    texts = []
    metadatas = []
    ids = []
    for name, description in SECTION_DESCRIPTIONS.items():
        texts.append(description)
        metadatas.append({"section": name})
        ids.append(name)

    # 4. Add them to the collection (ChromaDB embeds each description now, once)
    store.add_texts(texts=texts, metadatas=metadatas, ids=ids)
    return store


def match_heading(store: Chroma, heading: str) -> tuple:
    """Find the section whose description is closest in meaning to a heading."""
    # 1. Ask ChromaDB for the single closest description (k=1)
    results = store.similarity_search_with_score(heading, k=1)
    closest = results[0][0]
    distance = results[0][1]

    # 2. ChromaDB gives a distance (0 = identical); turn it into a similarity (1 = identical)
    similarity = round(1 - distance, 3)

    # 3. Only accept the match if it is similar enough
    if similarity >= HEADING_MATCH_THRESHOLD:
        section = closest.metadata["section"]
    else:
        section = None
    return section, similarity


def split_sections(text: str, store: Chroma) -> dict:
    """Split resume text into sections using its headings: keywords first, then ChromaDB."""
    # Start every section as empty text
    sections = {}
    for name in SECTION_HEADINGS:
        sections[name] = ""

    current = "contact"   # text before the first heading is usually the name and contact details

    for line in text.split("\n"):
        stripped = line.strip()

        # 1. Keep only the letters, so "P E R S O N A L  P R O F I L E" becomes "personalprofile"
        letters = ""
        for ch in stripped.lower():
            if ch.isalpha():
                letters += ch

        # 2. Decide if the line looks like a heading
        if len(letters) == 0:
            looks_like_heading = False      # empty line, or only numbers and symbols
        elif len(letters) > 35:
            looks_like_heading = False      # too long to be a heading
        elif stripped.isupper():
            looks_like_heading = True       # e.g. "PROFILE SUMMARY"
        elif stripped.istitle():
            looks_like_heading = True       # e.g. "Professional Experience"
        elif stripped.endswith(":"):
            looks_like_heading = True       # e.g. "Certifications:"
        else:
            looks_like_heading = False      # a normal sentence or list item

        
        # 3. Find the longest (most specific) keyword in the line, and the section it belongs to
        keyword_section = None
        longest = 0
        for section, keywords in SECTION_HEADINGS.items():
            for keyword in keywords:
                if keyword in letters:
                    if len(keyword) > longest:
                        keyword_section = section
                        longest = len(keyword)

        # 4. Decide which section this line starts (None means it is a normal line)
        if not looks_like_heading:
            new_section = None                                          # not a heading
        elif keyword_section is not None:
            new_section = keyword_section                               # heading matched by a keyword
        else:
            new_section, similarity = match_heading(store, stripped)    # heading with no keyword: ask ChromaDB

        # 5. A heading switches the current section; any other line is added to it
        if new_section is None:
            sections[current] += line + "\n"
        else:
            current = new_section

    # 6. Tidy up extra blank lines at the start and end of each section
    for name in sections:
        sections[name] = sections[name].strip()
    return sections

RESUME_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are an impartial resume screening assistant. "
     "Check the resume ONLY against the numbered items given. "
     "Ignore name, gender, age, ethnicity, religion, nationality and any other "
     "personal details that are not related to the job.\n"
     "For each item, first copy the exact words from the resume that prove it as evidence. "
     "If no words in the resume directly prove the item, the evidence is \"\" and shows is false. "
     "Do not guess or infer: a related skill is not the same as a certification or qualification.\n"
     "Reply ONLY with JSON in exactly this format, with one entry per item:\n"
     '{{"candidate": "<name, or Unknown>", '
     '"checks": [{{"id": <item number>, "evidence": "<exact quote from the resume, or empty>", "shows": true or false}}], '
     '"summary": "<one or two sentences>"}}'),
    ("human",
     "Items to check:\n{rules}\n\n"
     "Resume:\n{resume}"),
])

def check_connection() -> bool:
    """Check that the Ollama server is reachable and the model is downloaded."""
    try:
        client = ollama.Client(host=OLLAMA_HOST)
        models = client.list().models
    except ConnectionError:
        print(f"Cannot reach Ollama at {OLLAMA_HOST}. Is it running? (docker compose up -d)")
        return False

    model_names = [m.model for m in models]   # e.g. ["mistral:latest"]
    found = any(name == MODEL_NAME or name.split(":")[0] == MODEL_NAME
                for name in model_names)
    if not found:
        print(f"Connected, but model '{MODEL_NAME}' is not downloaded. Found: {model_names}")
        print(f"Download it with: docker compose exec ollama ollama pull {MODEL_NAME}")
        return False

    print(f"Connected to {OLLAMA_HOST} and '{MODEL_NAME}' is ready.")
    return True

def get_llm() -> ChatOllama:
    """Create the connection to the Mistral model on the Ollama server."""
    return ChatOllama(
        model=MODEL_NAME,     # which model to use ("mistral")
        base_url=OLLAMA_HOST, # where the Ollama server is
        temperature=0,        # straight forward answers, no randomness
        format="json",        # force the model to reply with valid JSON
        seed=42,              # fixed randomness so the same input gives the same output
        num_ctx=8192                            
    )

def start_chat(rules: list[dict], resume_text: str) -> dict:
    """Send one resume and the business rules to Mistral and return its answer as a dict."""
    # 1. Turn the rules into a numbered list of text
    rules_text = ""
    number = 1
    for rule in rules:
        rules_text += f"{number}. {rule['text']}\n"
        number += 1

    # 2. Fill in the blanks in the prompt template
    prompt = RESUME_PROMPT.invoke({"rules": rules_text, "resume": resume_text})

    # 3. Send the prompt to Mistral and wait for the reply
    llm = get_llm()
    
    # print(prompt.to_string()) for debugging
    
    reply = llm.invoke(prompt)

    # 4. Convert the JSON text reply into a Python dictionary
    result = json.loads(reply.content)
    return result

def parse_resumes(folder: str = "data", output_file: str = "resumes.json") -> list[dict]:
    """Read every PDF in a folder, split valid ones into sections, save as JSON (invalid resumes last)."""
    valid = []
    invalid = []
    store = build_section_store()   # built once, reused for every resume


    for path in sorted(Path(folder).iterdir()):
        # 1. Skip anything that isn't a PDF (.lower() so ".PDF" also counts)
        if path.suffix.lower() != ".pdf":
            continue
        else:
            resume = {"file": path.name, "status": "valid", "reason": "", "pages": 0, "text": "", "sections": {}}

            # 2. Pull the text out of every page
            try:
                reader = PdfReader(path)
                resume["pages"] = len(reader.pages)
                for page in reader.pages:
                    resume["text"] += page.extract_text() + "\n"
                resume["text"] = resume["text"].strip()
            except Exception as error:
                resume["status"] = "invalid"
                resume["reason"] = f"Could not read the PDF: {error}"

            # 3. Too little text = scanned picture; too much = not a single resume
            if resume["status"] == "valid" and len(resume["text"]) < MIN_TEXT_LENGTH:
                resume["status"] = "invalid"
                resume["reason"] = "No readable text (it may be a scanned image)"
            elif resume["status"] == "valid" and len(resume["text"]) > MAX_TEXT_LENGTH:
                resume["status"] = "invalid"
                resume["reason"] = f"Too long for one resume ({resume['pages']} pages)"

            # 4. Valid resumes are split into sections; both kinds are sorted into their list
            if resume["status"] == "valid":
                resume["sections"] = split_sections(resume["text"], store)
                valid.append(resume)
            else:
                invalid.append(resume)

    # 5. Valid resumes first, invalid ones at the bottom, then save as JSON
    resumes = valid + invalid
    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(resumes, file, indent=2, ensure_ascii=False)
    return resumes

if __name__ == "__main__":
    for r in parse_resumes():
        filled = []
        for name, text in r["sections"].items():
            if text:
                filled.append(name)
        print(r["status"], r["pages"], r["file"], r["reason"], "|", ", ".join(filled))

