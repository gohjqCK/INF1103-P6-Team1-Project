"""Data Manager: reads the resume PDFs, checks they are usable, and saves them as JSON for the AI Manager."""
import json
import logging
import os
from pathlib import Path

from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from pypdf import PdfReader

logging.getLogger("pypdf").setLevel(logging.CRITICAL)   # hide pypdf's font warnings

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

MIN_TEXT_LENGTH = 200     # less text than this usually means a scanned image, not a real text PDF
MAX_TEXT_LENGTH = 20000   # more than this won't fit in the AI's context window with the prompt

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
                if keyword in letters and len(keyword) > longest:
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


def save_resumes(resumes: list[dict], output_file: str) -> list[dict]:
    """Save the resumes as JSON with valid ones first and invalid ones at the bottom."""
    valid = []
    invalid = []
    for resume in resumes:
        if resume["status"] == "valid":
            valid.append(resume)
        else:
            invalid.append(resume)

    ordered = valid + invalid
    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(ordered, file, indent=2, ensure_ascii=False)
    return ordered


def parse_resumes(folder: str = "data", output_file: str = "resumes.json") -> list[dict]:
    """Read every PDF in a folder, split valid ones into sections, and save them as JSON (invalid ones last)."""
    store = build_section_store()   # built once, reused for every resume
    resumes = []

    for path in sorted(Path(folder).iterdir()):
        # 1. Only look at PDF files (.lower() so ".PDF" also counts)
        if path.suffix.lower() == ".pdf":

            # 2. Try to read the text from every page
            text = ""
            pages = 0
            error_message = ""
            try:
                reader = PdfReader(path)
                pages = len(reader.pages)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            except Exception as error:
                error_message = f"Could not read the PDF: {error}"
            text = text.strip()

            # 3. Decide whether the resume can be used
            if error_message != "":
                status = "invalid"
                reason = error_message
            elif len(text) < MIN_TEXT_LENGTH:
                status = "invalid"
                reason = "No readable text (it may be a scanned image)"
            elif len(text) > MAX_TEXT_LENGTH:
                status = "invalid"
                reason = f"Too long for one resume ({pages} pages)"
            else:
                status = "valid"
                reason = ""

            # 4. Valid resumes are also split into sections
            sections = {}
            if status == "valid":
                sections = split_sections(text, store)

            resumes.append({"file": path.name, "status": status, "reason": reason,
                            "pages": pages, "text": text, "sections": sections})

    # 5. Save as JSON: valid resumes first, invalid ones at the bottom
    return save_resumes(resumes, output_file)