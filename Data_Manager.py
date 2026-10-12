"""Data Manager: reads the resume PDFs, checks they are usable, and saves them as JSON for the AI Manager."""
import json
import logging
from pathlib import Path

from pypdf import PdfReader

logging.getLogger("pypdf").setLevel(logging.CRITICAL)   # hide pypdf's font warnings

MIN_TEXT_LENGTH = 200     # less text than this usually means a scanned image, not a real text PDF
MAX_TEXT_LENGTH = 20000   # more than this won't fit in the AI's context window with the prompt


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
    """Read every PDF in a folder, check it is usable, and save them all as JSON (invalid ones last)."""
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

            resumes.append({"file": path.name, "status": status, "reason": reason,
                            "pages": pages, "text": text})

    # 4. Save as JSON: valid resumes first, invalid ones at the bottom
    return save_resumes(resumes, output_file)
