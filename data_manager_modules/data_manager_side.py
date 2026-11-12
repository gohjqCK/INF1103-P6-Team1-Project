"""Orchestrates pipeline processing, file exports, and business rules."""
import io
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from pypdf import PdfReader

from data_manager_modules.data_manager_resume import Resume
from data_manager_modules.data_manager_supabase_handler import SupabaseHandler
from data_manager_modules.data_manager_resume_parser import ResumePDFParser


class DataManager:
    """Orchestrates ingestion, processing, exports, and business rules."""

    def __init__(self):
        self.db_handler = SupabaseHandler()
        self.parser = ResumePDFParser()

    def parse_pdf_bytes(self, file_name: str, pdf_bytes: bytes) -> Resume:
        """Extracts text from in-memory PDF bytes and returns a validated Resume object."""
        text = ""
        pages = 0
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            pages = len(reader.pages)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
            return Resume(file_name=file_name, raw_text=text, pages=pages)
        except Exception as err:
            return Resume(file_name=file_name, error_message=f"Could not read the PDF file: {err}")

    def upload_resume_bytes(
        self, file_name: str, pdf_bytes: bytes, company_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Parses PDF bytes, uploads the PDF to Supabase Storage, and registers it in resume_files & parsed_resumes."""
        resume_obj = self.parse_pdf_bytes(file_name, pdf_bytes)
        public_url = self.db_handler.upload_pdf_to_storage(file_name, pdf_bytes) or ""

        self.db_handler.register_resume_file(
            file_name=file_name,
            pdf_url=public_url,
            company_id=company_id,
            parsed_text=resume_obj.raw_text,
            pages=resume_obj.pages,
            status=resume_obj.status,
            invalid_reason=resume_obj.reason,
        )

        try:
            self.db_handler.export_parsed_resumes([resume_obj])
        except Exception:
            pass

        result = resume_obj.to_dict()
        result["pdf_url"] = public_url
        result["company_id"] = company_id
        return result

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

    def process_all_resumes(self, company_id: int) -> List[Dict[str, Any]]:
        """Loads a company's resumes from Supabase and returns them as dicts for the AI Manager."""
        db_files = self.db_handler.fetch_resume_files(company_id=company_id)

        if not db_files:
            print(f"No records found in 'resume_files' table for company ID {company_id}.")
            return []

        resumes: List[Dict[str, Any]] = []
        for record in db_files:
            filename = record["file_name"]
            parsed_text = record.get("parsed_text") or ""
            pages = record.get("pages") or 0
            status = record.get("status") or "valid"
            # Trust the status column: only an invalid record's reason is an error message
            error_message = (record.get("invalid_reason") or "") if status == "invalid" else ""

            # If text or error is already stored in DB, instantiate Resume directly without streaming from URL again
            if parsed_text or error_message:
                resume_obj = Resume(
                    file_name=filename,
                    raw_text=parsed_text,
                    pages=pages,
                    error_message=error_message,
                )
            else:
                # Fallback: re-parse from URL if DB text is missing
                pdf_url = record.get("pdf_url")
                resume_obj = self.parser.parse_from_url(filename, pdf_url)

            resume_dict = resume_obj.to_dict()
            resume_dict["id"] = record.get("id")
            resumes.append(resume_dict)

        return resumes

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

    @staticmethod
    def save_businessrules(businessrules: List[Any], filepath: str = "Business_Rules.json"):
        """Saves business rule configurations to disk."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(businessrules, f, indent=4)

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
