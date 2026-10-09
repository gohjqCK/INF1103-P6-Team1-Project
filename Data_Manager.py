import glob
import json
import os
import re
import pdfplumber

RESUME_FOLDER = "./data"
OUTPUT_JSON = "converted_resumes.json"

# Regex patterns & Keyword lists
EMAIL_PATTERN = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
PHONE_PATTERN = r"\(?\b\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b"
SKILL_KEYWORDS = [
    "Python",
    "SQL",
    "Java",
    "JavaScript",
    "React",
    "Docker",
    "AWS",
    "Project Management",
    "Excel",
    "Machine Learning",
    "Git",
    "Cloud management",
    "Database management",
    "IT Support",
    "System documentation",
    "Troubleshooting",
]

COMMON_JOB_TITLES = [
    "Software Engineer",
    "Senior Software Engineer",
    "Frontend Developer",
    "Backend Developer",
    "Full Stack Developer",
    "Data Scientist",
    "Data Analyst",
    "Project Manager",
    "Product Manager",
    "DevOps Engineer",
    "Systems Administrator",
    "Business Analyst",
    "QA Engineer",
    "UI/UX Designer",
    "Marketing Manager",
    "IT Manager",
    "Database Manager",
    "Database Architect",
    "Database Engineer",
    "Database Developer",
    "Software Architect",
    "Software Developer",
    "Systems Engineer",
    "Systems Developer",
    "Systems Architect",
    "IT Developer",
    "IT Engineer",
]


def extract_full_pdf_text(pdf):
    """Function to extract ALL raw text across all pages of a PDF into a single string."""
    page_texts = []
    text_lines = []
    for page in pdf.pages:
        text = page.extract_text()
        if text:
            page_texts.append(text)
            text_lines.extend(
                [line.strip() for line in text.split("\n") if line.strip()]
            )

    raw_combined = " ".join(page_texts)
    clean_text = re.sub(r"\s+", " ", raw_combined).strip()

    return clean_text, text_lines


def extract_years_of_experience(text):
    """Business Rule: Find explicit years or calculate from date ranges."""
    pattern = r"(\d{1,2})\+?\s*(?:years?|yrs?)(?:\s+of)?\s+experience"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return int(match.group(1))

    years = re.findall(r"\b(20\d{2}|19\d{2})\b", text)
    if len(years) >= 2:
        years_sorted = sorted([int(y) for y in years])
        span = years_sorted[-1] - years_sorted[0]
        if 0 < span <= 45:
            return span

    return "Not Specified"


def extract_work_experience(text):
    """Business Rule: Extract job titles found in the resume text."""
    found_titles = []

    for title in COMMON_JOB_TITLES:
        if re.search(rf"\b{re.escape(title)}\b", text, re.IGNORECASE):
            found_titles.append(title)

    pattern = r"(?:Position|Role|Title):\s*([A-Za-z\s]+)"
    matches = re.findall(pattern, text, re.IGNORECASE)
    for match in matches:
        cleaned_match = match.strip()
        if (
            cleaned_match
            and len(cleaned_match) < 40
            and cleaned_match not in found_titles
        ):
            found_titles.append(cleaned_match)

    return found_titles if found_titles else ["Not Specified"]


def extract_education(text):
    """Business Rule: Detect degrees mentioned in the text."""
    degrees = []
    if re.search(r"\b(ph\.?d|doctorate)\b", text, re.IGNORECASE):
        degrees.append("PhD")
    if re.search(r"\b(master|m\.s|m\.a|mba)\b", text, re.IGNORECASE):
        degrees.append("Master's")
    if re.search(r"\b(bachelor|b\.s|b\.a|b\.tech)\b", text, re.IGNORECASE):
        degrees.append("Bachelor's")
    if re.search(r"\b(diploma)\b", text, re.IGNORECASE):
        degrees.append("Diploma")

    return degrees if degrees else ["Not Specified"]


# Master dictionary structure with 'candidates' key
extracted_database = {"candidates": {}}

# Process each PDF resume
for file_path in glob.glob(os.path.join(RESUME_FOLDER, "*.pdf")):
    filename = os.path.basename(file_path)

    with pdfplumber.open(file_path) as pdf:
        clean_text, text_lines = extract_full_pdf_text(pdf)

    # Extract name (first non-header line)
    candidate_name = "Unknown"
    for line in text_lines:
        if not re.search(
            r"resume|curriculum vitae|cv|page", line, re.IGNORECASE
        ):
            candidate_name = line
            break

    # Extract fields
    email_match = re.search(EMAIL_PATTERN, clean_text)
    phone_match = re.search(PHONE_PATTERN, clean_text)

    found_skills = [
        skill
        for skill in SKILL_KEYWORDS
        if re.search(rf"\b{re.escape(skill)}\b", clean_text, re.IGNORECASE)
    ]

    exp_titles = extract_work_experience(clean_text)
    education_degrees = extract_education(clean_text)

    # INSIDE THE LOOP NOW:
    json_candidate_entity = {
        "Name": candidate_name,
        "Email": email_match.group(0) if email_match else "N/A",
        "Phone": phone_match.group(0) if phone_match else "N/A",
        "Est_Years_Exp": extract_years_of_experience(clean_text),
        "Experience_Titles": exp_titles,
        "Education": education_degrees,
        "Skills": found_skills if found_skills else ["None Detected"],
        "File_Name": filename,
        "Full_PDF_Text": clean_text,
    }

    # Store under master "candidates" object
    extracted_database["candidates"][filename] = json_candidate_entity

# Save to JSON file after processing all files
with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(extracted_database, f, indent=4, ensure_ascii=False)

print(f"Successfully extracted {len(extracted_database['candidates'])} resumes into '{OUTPUT_JSON}'.")