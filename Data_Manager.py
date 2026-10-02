import glob
import os
import re
import json
import pdfplumber

RESUME_FOLDER = "./data"
OUTPUT_JSON = "converted_resumes.json"

# Regex patterns & Keyword lists
EMAIL_PATTERN = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
PHONE_PATTERN = r"\(?\b\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b"
SKILL_KEYWORDS = [
    "Python", "SQL", "Java", "JavaScript", "React", 
    "Docker", "AWS", "Project Management", "Excel", 
    "Machine Learning", "Git"
]
# Common job titles to search for across candidate history
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
    "Accountant",
    "Marketing Manager",
    "IT Manager",
]

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

    # 1. Direct Keyword Matching for known job titles
    for title in COMMON_JOB_TITLES:
        if re.search(rf"\b{re.escape(title)}\b", text, re.IGNORECASE):
            found_titles.append(title)

    # 2. Regex fallback: Look for line patterns in Experience sections (e.g., "Role: Developer" or "Engineer - Company")
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
    if re.search(r"\b(diploma|b\.s|b\.a|b\.tech)\b", text, re.IGNORECASE):
        degrees.append("Diploma")

    return degrees if degrees else ["Not Specified"]

candidates_dictionary = {}

# Process each PDF resume
for file_path in glob.glob(os.path.join(RESUME_FOLDER, "*.pdf")):
    filename = os.path.basename(file_path)

    # Combine all page text into one clean string per PDF
    full_text_pages = []
    text_lines = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                full_text_pages.append(page_text)
                text_lines.extend([line.strip() for line in page_text.split("\n") if line.strip()])

    raw_text = " ".join(full_text_pages)
    clean_text = re.sub(r"\s+", " ", raw_text).strip()

    # Extract name (first non-header line)
    candidate_name = "Unknown"
    for line in text_lines:
        if not re.search(r"resume|curriculum vitae|cv|page", line, re.IGNORECASE):
            candidate_name = line
            break

    # Extract fields
    email_match = re.search(EMAIL_PATTERN, clean_text)
    phone_match = re.search(PHONE_PATTERN, clean_text)

    found_skills = [
        skill for skill in SKILL_KEYWORDS 
        if re.search(rf"\b{re.escape(skill)}\b", clean_text, re.IGNORECASE)
    ]

    # Create entity dictionary with keys matching the previous headers
    candidate_entity = {
        "Name": candidate_name,
        "Email": email_match.group(0) if email_match else "N/A",
        "Phone": phone_match.group(0) if phone_match else "N/A",
        "Est_Years_Exp": extract_years_of_experience(clean_text),
        "Experience_Titles": extract_work_experience(clean_text),        
        "Education": extract_education(clean_text),
        "Skills": found_skills if found_skills else ["None Detected"],
        "File_Name": filename
    }

    # Store using the filename (or candidate name) as the primary key
    candidates_dictionary[filename] = candidate_entity

# Save to JSON file
with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(candidates_dictionary, f, indent=4, ensure_ascii=False)

print(f"Successfully processed {len(candidates_dictionary)} resumes into '{OUTPUT_JSON}'.")