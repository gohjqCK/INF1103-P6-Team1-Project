"""Orchestrates pipeline processing, file exports, and business rules."""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple

from data_manager_modules.data_manager_resume import Resume
from data_manager_modules.data_manager_supabase_handler import SupabaseHandler
from data_manager_modules.data_manager_resume_parser import ResumePDFParser


class DataManager:
    """Orchestrates ingestion, processing, exports, and business rules."""
    CLOUD_READY = True

    def __init__(self):
        self.db_handler = SupabaseHandler()
        self.parser = ResumePDFParser()

    def upload_local_folder(
        self, folder_path: str, company_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Scans a local folder for PDFs and uploads each to Supabase for the given company_id."""
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            return []

        uploaded: List[Dict[str, Any]] = []
        for pdf_file in sorted(folder.glob("*.pdf")):
            try:
                pdf_bytes = pdf_file.read_bytes()
                res = self.upload_resume_bytes(pdf_file.name, pdf_bytes, company_id=company_id)
                uploaded.append(res)
            except Exception as err:
                print(f"Error uploading {pdf_file.name}: {err}")
        return uploaded

    def process_all_resumes(
        self, output_file: str = "resumes.json", company_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Fetches resume records from Supabase for this company, parses/validates them, saves resumes.json, and returns dicts."""
        db_files = self.db_handler.fetch_resume_files(company_id=company_id)

        if not db_files:
            print(f"No records found in 'resume_files' table for company ID {company_id}.")
            return []

        processed_resumes: List[Tuple[Optional[int], Resume]] = []
        for record in db_files:
            filename = record["file_name"]
            parsed_text = record.get("parsed_text") or record.get("text", "")
            pages = record.get("pages") or 0
            status = record.get("status") or "valid"
            error_message = record.get("invalid_reason", "") if status == "invalid" else ""

            # If text or error is already stored in DB, instantiate Resume directly without streaming from URL again
            if parsed_text or error_message:
                resume_obj = Resume(
                    file_name=filename,
                    raw_text=parsed_text,
                    pages=pages,
                    error_message=error_message,
                )
            else:
                pdf_url = record.get("pdf_url")
                resume_obj = self.parser.parse_from_url(filename, pdf_url)

            processed_resumes.append((record.get("id"), resume_obj))

        valid_pairs = sorted(
            [(rid, r) for rid, r in processed_resumes if r.status == "valid"],
            key=lambda item: item[1].file_name,
        )
        invalid_pairs = sorted(
            [(rid, r) for rid, r in processed_resumes if r.status == "invalid"],
            key=lambda item: item[1].file_name,
        )
        ordered_pairs = valid_pairs + invalid_pairs
        ordered_resumes = [r for _, r in ordered_pairs]

        self.save_resumes_to_json(ordered_resumes, output_file)
        result_dicts: List[Dict[str, Any]] = []
        for rid, resume_obj in ordered_pairs:
            d = resume_obj.to_dict()
            d["id"] = rid
            result_dicts.append(d)
        return result_dicts

    @staticmethod
    def save_resumes_to_json(resumes: List[Resume], output_file: str) -> List[Dict[str, Any]]:
        """Saves a list of Resume objects to a JSON file."""
        ordered_dicts = [r.to_dict() for r in resumes]
        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(ordered_dicts, file, indent=2, ensure_ascii=False)
        return ordered_dicts

    @staticmethod
    def date_time_format_func() -> str:
        """Returns the current timestamp string in SGT format."""
        sgt = timezone(timedelta(hours=8))
        dt = datetime.now(sgt)
        return dt.strftime("%Y-%m-%d %H-%M-%S")

    def outputfile_func(self, accepted: List[Any], rejected: List[Any], invalid: List[Any], output_folder: str = "."):
        """Outputs categorized evaluation lists to a timestamped JSON file."""
        keynames = ["accepted", "rejected", "invalid"]
        overall_resume = [accepted, rejected, invalid]
        categorized_list = [{keynames[i]: overall_resume[i]} for i in range(3)]

        filename = f"filtered_resume_{self.date_time_format_func()}.json"
        folder_path = Path(output_folder)
        folder_path.mkdir(parents=True, exist_ok=True)
        filepath = folder_path / filename

        with open(filepath, "w", encoding="utf-8") as file:
            json.dump(categorized_list, file, ensure_ascii=False, indent=4)

# Handle business rules data

    @staticmethod
    def get_businessrules(filepath: str = "Business_Rules.json") -> List[Any]:
        """Loads business rules from disk or creates an empty JSON file."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump([], f, indent=4)
            return []

    def list_company_rule_sets(self, company_id: int) -> List[Dict[str, Any]]:
        """Lists all business rule sets for a given company ordered by ID ascending."""
        return self.db_handler.list_company_rule_sets(company_id)

    def create_company_rule_set(
        self,
        company_id: int,
        set_name: str,
        rules: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Creates a new named business rule set for a company."""
        return self.db_handler.create_company_rule_set(company_id, set_name, rules)

    def update_company_rule_set(
        self,
        company_id: int,
        rule_set_id: int,
        set_name: Optional[str] = None,
        rules: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Updates an existing business rule set in place."""
        return self.db_handler.update_company_rule_set(company_id, rule_set_id, set_name, rules)

    def delete_company_rule_set(self, company_id: int, rule_set_id: int) -> bool:
        """Deletes a business rule set and cleans up linked results."""
        return self.db_handler.delete_company_rule_set(company_id, rule_set_id)

# Handle companies data

    def create_company(
        self, company_name: str, passcode_hash: str, owner_id: int, invite_code: str
    ) -> Dict[str, Any]:
        return self.db_handler.create_company(company_name, passcode_hash, owner_id, invite_code)

    def get_company_by_invite(self, invite_code: str) -> Optional[Dict[str, Any]]:
        return self.db_handler.get_company_by_invite(invite_code)

    def add_company_member(self, company_id: int, user_id: int) -> None:
        self.db_handler.add_company_member(company_id, user_id)

    def list_user_companies(self, user_id: int) -> List[Dict[str, Any]]:
        return self.db_handler.list_user_companies(user_id)

# Handle resume files

    def parse_pdf_bytes(self, file_name: str, pdf_bytes: bytes) -> Resume:
        """Parses raw PDF bytes in memory using ResumePDFParser."""
        return self.parser.parse_pdf_bytes(file_name, pdf_bytes)

    def upload_resume_bytes(
        self, file_name: str, pdf_bytes: bytes, company_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Parses, uploads to Supabase Storage 'resume_files', and registers metadata."""
        return self.db_handler.upload_resume_bytes(file_name, pdf_bytes, company_id)

    def list_company_resumes(self, company_id: int) -> List[Dict[str, Any]]:
        """Lists all uploaded resumes for a specific company_id."""
        return self.db_handler.list_company_resumes(company_id)

    def download_resume_bytes(self, company_id: int, file_name: str) -> Optional[bytes]:
        """Downloads raw PDF bytes from Storage for a company's resume."""
        return self.db_handler.download_resume_bytes(company_id, file_name)

    def delete_company_resume(self, company_id: int, file_name: str) -> bool:
        """Deletes a single resume from Storage and the resume_files table."""
        return self.db_handler.delete_company_resume(company_id, file_name)

    def clear_company_resumes(self, company_id: int) -> None:
        """Deletes all resumes belonging to company_id from Storage and resume_files."""
        self.db_handler.clear_company_resumes(company_id)

# Handle results & AI Summary persistence

    def save_screening_results(
        self,
        company_id: int,
        ranked_candidates: List[Dict[str, Any]],
        summary_data: Optional[Dict[str, Any]],
        filtered_resumes: Optional[Dict[str, Any]] = None,
        business_rules_id: Optional[int] = None,
    ) -> None:
        """Persists screening results and optional AI summary to Supabase."""
        self.db_handler.save_screening_results(
            company_id=company_id,
            ranked_candidates=ranked_candidates,
            summary_data=summary_data,
            filtered_resumes=filtered_resumes,
            business_rules_id=business_rules_id,
        )

    def get_screening_results(
        self,
        company_id: int,
        business_rules_id: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Fetches the latest screening results and linked AI summary."""
        return self.db_handler.get_screening_results(
            company_id=company_id,
            business_rules_id=business_rules_id,
        )
