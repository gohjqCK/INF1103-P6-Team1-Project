# Handles API connectivity and queries for Supabase DB
import os
from typing import List, Dict, Any, Optional
from supabase import Client, create_client
from data_manager_modules.data_manager_resume import Resume

class SupabaseHandler:
    # Handles database transactions with Supabase

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        self.url = url or os.getenv("SUPABASE_URL", "https://gkrrffsbedfodcnnvhys.supabase.co")
        self.key = key or os.getenv("SUPABASE_KEY", "sb_publishable_-_fcFwwIF60dlOMaC_9xMQ_YFX98Q6D")
        self.client: Client = create_client(self.url, self.key)

    def upload_pdf_to_storage(self, file_name: str, pdf_bytes: bytes, bucket_name: str = "resumes") -> Optional[str]:
        """Uploads raw PDF bytes to a Supabase Storage bucket and returns its public URL."""
        try:
            # Upload file bytes to bucket (overwrites if file_name exists)
            self.client.storage.from_(bucket_name).upload(
                path=file_name,
                file=pdf_bytes,
                file_options={"content-type": "application/pdf", "upsert": "true"}
            )
            # Retrieve the public access URL
            public_url = self.client.storage.from_(bucket_name).get_public_url(file_name)
            return public_url
        except Exception as err:
            print(f"Error uploading {file_name} to Supabase Storage: {err}")
            return None

    def register_resume_file(
        self,
        file_name: str,
        pdf_url: str,
        company_id: Optional[int] = None,
        parsed_text: str = "",
        pages: int = 0,
        status: str = "valid",
        invalid_reason: str = ""
    ) -> None:
        """Inserts or updates a complete resume record matching the new schema."""
        record = {
            "company_id": company_id,
            "file_name": file_name,
            "pdf_url": pdf_url,
            "parsed_text": parsed_text,
            "pages": pages,
            "status": status,
            "invalid_reason": invalid_reason
        }
        # Upserts into resume_files table
        self.client.table("resume_files").upsert(record, on_conflict="file_name").execute()

    def fetch_resume_files(self) -> List[Dict[str, Any]]:
        # Retrieves file metadata records from the resume_files table
        print("Fetching file list from Supabase 'resume_files' table...")
        response = self.client.table("resume_files").select("id, file_name, pdf_url").execute()
        return response.data or []

    def export_parsed_resumes(self, resumes: List[Resume]) -> None:
        # Upserts processed Resume objects into the parsed_resumes table
        records = [resume.to_db_record() for resume in resumes]
        if records:
            self.client.table("parsed_resumes").upsert(records, on_conflict="file_name").execute()
            print(f"Successfully uploaded {len(records)} parsed resumes into Supabase 'parsed_resumes' table.")