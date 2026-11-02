"""Data Manager: reads resume PDFs from Supabase Storage/Table, checks usability,
and exports parsed candidate data into the Supabase 'parsed_resumes' table."""
import io
import json
import logging
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
import urllib.request

from pypdf import PdfReader
from supabase import Client, create_client

# Hide pypdf font warnings
logging.getLogger("pypdf").setLevel(logging.CRITICAL)

# ==========================================
# SUPABASE CONFIGURATION
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://gkrrffsbedfodcnnvhys.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_-_fcFwwIF60dlOMaC_9xMQ_YFX98Q6D")  # Paste your key here

MIN_TEXT_LENGTH = 200     # less text than this usually means a scanned image, not a real text PDF
MAX_TEXT_LENGTH = 20000   # upper bound for context window


def export_to_supabase_parsed_resumes(supabase: Client, resumes: list[dict]):
    """Uploads structured parsed resume data into the 'parsed_resumes' table on Supabase."""
    records = []
    for item in resumes:
        record = {
            "file_name": item["file"],
            "status": item["status"],
            "reason": item["reason"],
            "pages": item["pages"],
            "full_text": item["text"],
        }
        records.append(record)

    if records:
        # Uses insert to avoid requiring ON CONFLICT SQL constraints
        response = (
            supabase.table("parsed_resumes")
           .upsert(records, on_conflict="file_name")
          .execute()
        )
        print(f"Successfully uploaded {len(records)} parsed resumes into Supabase 'parsed_resumes' table.")


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


def parse_resumes_from_supabase(output_file: str = "resumes.json") -> list[dict]:
    """1. Fetches file list & URLs from Supabase table 'resume_files'.
       2. Parses PDF stream using pypdf directly from memory.
       3. Uploads parsed outputs into Supabase table 'parsed_resumes'.
    """
    # Initialize Supabase client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 1. Fetch file list from 'resume_files' table
    print("Fetching file list from Supabase 'resume_files' table...")
    response = supabase.table("resume_files").select("id, file_name, pdf_url").execute()
    db_files = response.data

    if not db_files:
        print("No records found in 'resume_files' table.")
        return []

    resumes = []

    # 2. Iterate through records and process PDFs directly from their URL
    for record in db_files:
        filename = record["file_name"]
        pdf_url = record.get("pdf_url")

        print(f"Processing: {filename}...")
        text = ""
        pages = 0
        error_message = ""

        if not pdf_url:
            error_message = "No valid pdf_url found in database entry."
        else:
            try:
                # Stream PDF bytes directly into memory via urllib request
                req = urllib.request.Request(pdf_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req) as response_stream:
                    pdf_bytes = response_stream.read()
                
                # Load PDF into PdfReader via in-memory stream
                reader = PdfReader(io.BytesIO(pdf_bytes))
                pages = len(reader.pages)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
            except Exception as error:
                error_message = f"Could not read the PDF stream: {error}"

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

        resumes.append({
            "file": filename,
            "status": status,
            "reason": reason,
            "pages": pages,
            "text": text
        })

    # Save backup copy locally (valid resumes first, invalid last)
    ordered_resumes = save_resumes(resumes, output_file)

    # 4. Export to Supabase 'parsed_resumes' table
    export_to_supabase_parsed_resumes(supabase, ordered_resumes)

    return ordered_resumes


# Date time format helper
def date_time_format_func():
    sgt = timezone(timedelta(hours=8))
    dt = datetime.now(sgt)
    time_string = dt.strftime("%Y-%m-%d %H-%M-%S")
    return time_string 


# Outputs filtered resumes to JSON file
def outputfile_func(accepted, rejected, invalid, output_folder="."):
    keyname = ["accepted", "rejected", "invalid"]
    overall_resume = [accepted, rejected, invalid]
    resume_catogerised_list = []
    filename = "filtered_resume_" + str(date_time_format_func()) + ".json"
    folder_path = Path(output_folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    filepath = folder_path / filename
    for index in range(3):
        dictionary_variable = {}
        dictionary_variable[keyname[index]] = overall_resume[index]
        resume_catogerised_list.append(dictionary_variable)
    with open(filepath, "w", encoding="utf-8") as file:
        json.dump(resume_catogerised_list, file, ensure_ascii=False, indent=4)


def save_businessrules(businessrules):
    with open("Business_Rules.json", "w", encoding="utf-8") as f:
        json.dump(businessrules, f, indent=4)


def get_businessrules():
    try:
        with open("Business_Rules.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        with open("Business_Rules.json", "w", encoding="utf-8") as f:
            json.dump([], f, indent=4)
        return []


if __name__ == "__main__":
    parse_resumes_from_supabase()