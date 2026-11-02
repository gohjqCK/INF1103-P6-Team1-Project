"""Orchestrates pipeline processing, file exports, and business rules."""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from data_manager_modules.data_manager_resume import Resume
from data_manager_modules.data_manager_supabase_handler import SupabaseHandler
from data_manager_modules.data_manager_resume_parser import ResumePDFParser


class DataManager:
    """Orchestrates ingestion, processing, exports, and business rules."""

    def __init__(self):
        self.db_handler = SupabaseHandler()
        self.parser = ResumePDFParser()

    def process_all_resumes(self, output_file: str = "resumes.json") -> List[Dict[str, Any]]:
        """Executes full pipeline: Fetch -> Parse -> Sort -> Local JSON -> Supabase Export."""
        db_files = self.db_handler.fetch_resume_files()
        if not db_files:
            print("No records found in 'resume_files' table.")
            return []

        processed_resumes: List[Resume] = []
        for record in db_files:
            filename = record["file_name"]
            pdf_url = record.get("pdf_url")
            print(f"Processing: {filename}...")

            resume_obj = self.parser.parse_from_url(filename, pdf_url)
            processed_resumes.append(resume_obj)

        # Sort: valid resumes first, invalid last
        valid_resumes = [r for r in processed_resumes if r.status == "valid"]
        invalid_resumes = [r for r in processed_resumes if r.status != "valid"]
        ordered_resumes = valid_resumes + invalid_resumes

        # Save backup local JSON file
        self.save_resumes_to_json(ordered_resumes, output_file)

        # Export to Supabase parsed_resumes table
        self.db_handler.export_parsed_resumes(ordered_resumes)

        return [r.to_dict() for r in ordered_resumes]

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