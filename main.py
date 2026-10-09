import os
import re
import pandas as pd
import pdfplumber
import Data_Manager
import IO_manager
import Logic_Manager
import AI_Manager

def read_pdf(fp):
    try:
        with pdfplumber.open(fp) as p: return "\n".join(pg.extract_text() or "" for pg in p.pages).strip()
    except: return ""

def get_data(text, fn):
    em, ph = re.search(Data_Manager.EMAIL_PATTERN, text), re.search(Data_Manager.PHONE_PATTERN, text)
    sk = [s for s in Data_Manager.SKILL_KEYWORDS if re.search(rf"\b{re.escape(s)}\b", text, re.I)]
    nl = [l.strip() for l in text.splitlines() if l.strip()]
    name = next((l for l in nl if not re.search(r"resume|curriculum vitae|cv|page", l, re.I)), "Unknown")
    return {
        "name": name, "email": em.group(0) if em else "N/A", "phone_number": ph.group(0) if ph else "N/A",
        "address": "Not Specified", "Est_Years_Exp": Data_Manager.extract_years_of_experience(text),
        "Experience_Titles": "; ".join(Data_Manager.extract_work_experience(text)),
        "Education": "; ".join(Data_Manager.extract_education(text)),
        "Skills": "; ".join(sk) if sk else "None Detected", "SoftSkills": sk[0] if sk else "General", "File_Name": fn
    }

def process_and_rank_resumes():
    cfg = IO_manager.get_employer_inputs()
    ai_on = AI_Manager.check_connection()
    resumes = []
    
    for r in AI_Manager.parse_resumes(folder=cfg["pdf_directory"]):
        txt = r.get("text", "").strip()
        if len(txt) < 50: txt = read_pdf(os.path.join(cfg["pdf_directory"], r["file"]))
        if txt: resumes.append({**r, "text": txt})

    if not resumes:
        return IO_manager.display_error("No readable PDF resumes found. Exiting.")

    rules = [{"text": re.sub(r"^\d+[\.\)]\s*|^[\-\*]\s*", "", l).strip()} for l in cfg["business_rules"].splitlines() if l.strip()]
    evals = []  
    logic_data = []

    for r in resumes:
        m = get_data(r["text"], r["file"])
        logic_data.append(dict(m))
        passed, ai_res = 0, None
        if ai_on:
            try:
                ai_res = AI_Manager.start_chat(rules, r["text"])
                passed = sum(1 for c in ai_res.get("checks", []) if c.get("shows"))
                if ai_res.get("candidate") and ai_res["candidate"].lower() != "unknown":
                    m["name"] = ai_res["candidate"].strip()
            except Exception as e: IO_manager.display_error(f"AI error for {r['file']}: {e}")
        
        evals.append({"m": m, "ai": ai_res, "p": passed, "score": (passed / len(rules) * 100) if rules else 0.0})

    evals.sort(key=lambda x: x["score"], reverse=True)
    pd.DataFrame([e["m"] for e in evals]).to_csv("evaluated_candidates.csv", index=False)
    
    IO_manager.display_message("\n--- LOGIC MANAGER: ANONYMIZATION & STATS ---")
    Logic_Manager.resume_Stats(Logic_Manager.mask_Resume(logic_data))

    top = min(cfg["top_n"], len(evals))
    IO_manager.display_message(f"\n================ TOP {top} CANDIDATE RESULTS ================")
    for i, e in enumerate(evals[:top], 1):
        m, ai = e["m"], e["ai"]
        IO_manager.display_message(f"\n[Rank #{i}] {m['name']} ({m['File_Name']})")
        IO_manager.display_message(f"  Score: {e['score']:.1f}% ({e['p']}/{len(rules)} criteria met)")
        IO_manager.display_message(f"  Experience: {m['Est_Years_Exp']} yrs | Roles: {m['Experience_Titles']}")
        IO_manager.display_message(f"  Education: {m['Education']} | Skills: {m['Skills']}")
        if ai:
            IO_manager.display_message(f"  Summary: {ai.get('summary', 'N/A')}")
            for c in ai.get("checks", []):
                cid = c.get("id")
                st = "[✓] PASS" if c.get("shows") else "[✗] FAIL"
                rt = rules[cid - 1]["text"] if cid <= len(rules) else f"Rule {cid}"
                ev = c.get("evidence", "").strip().replace("\n", " ") or "No direct evidence found"
                IO_manager.display_message(f"    {st} - Rule #{cid} ({rt}): {ev}")

    IO_manager.display_success("\nResume checking complete.")

if __name__ == "__main__":
    process_and_rank_resumes()