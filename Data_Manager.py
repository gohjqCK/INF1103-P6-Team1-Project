"""Data Manager: reads the resume PDFs, checks they are usable, and saves them as JSON for the AI Manager."""
import json
import logging
from pathlib import Path
from datetime import datetime

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

#date time format
def date_time_format_func():
    from datetime import timezone, timedelta
    sgt = timezone(timedelta(hours=8))
    dt = datetime.now(sgt)

    time_string = dt.strftime("%Y-%m-%d %H-%M-%S")
    return time_string 

#outputs filtered resumes to json file
def outputfile_func(accepted, rejected, invalid, output_folder="."):
    keyname=["accepted","rejected","invalid"]
    overall_resume=[accepted,rejected,invalid]
    resume_catogerised_list=[]
    filename= "filtered_resume_"+str(date_time_format_func())+".json"
    folder_path = Path(output_folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    filepath = folder_path / filename
    for index in range(3):
        dictionary_variable={}
        dictionary_variable[keyname[index]]=overall_resume[index]
        resume_catogerised_list.append(dictionary_variable)
    with open(filepath,"w", encoding="utf-8") as file:
            json.dump(resume_catogerised_list,file, ensure_ascii=False, indent=4)