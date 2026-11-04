"""Handles API connectivity and queries for Supabase tables."""
import os
from typing import List, Dict, Any, Optional
from supabase import Client, create_client
from data_manager_modules.data_manager_resume import Resume


class SupabaseHandler:
    """Handles database transactions with Supabase."""

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        self.url = url or os.getenv("SUPABASE_URL", "https://gkrrffsbedfodcnnvhys.supabase.co")
        self.key = key or os.getenv("SUPABASE_KEY", "sb_publishable_-_fcFwwIF60dlOMaC_9xMQ_YFX98Q6D")
        self.client: Client = create_client(self.url, self.key)

    def fetch_resume_files(self) -> List[Dict[str, Any]]:
        """Retrieves file metadata records from the resume_files table."""
        print("Fetching file list from Supabase 'resume_files' table...")
        response = self.client.table("resume_files").select("id, file_name, pdf_url").execute()
        return response.data or []

    def export_parsed_resumes(self, resumes: List[Resume]) -> None:
        """Upserts processed Resume objects into the parsed_resumes table."""
        records = [resume.to_db_record() for resume in resumes]
        if records:
            self.client.table("parsed_resumes").upsert(records, on_conflict="file_name").execute()
            print(f"Successfully uploaded {len(records)} parsed resumes into Supabase 'parsed_resumes' table.")