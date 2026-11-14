import unittest
from unittest.mock import MagicMock
from data_manager_modules.data_manager_resume import Resume
from data_manager_modules.data_manager_side import DataManager


class TestDataManagerPipeline(unittest.TestCase):
    def setUp(self):
        self.dm = DataManager()
        self.dm.db_handler = MagicMock()
        self.dm.save_resumes_to_json = MagicMock()

    def test_status_valid_with_ok_reason(self):
        """Ensures that records with status='valid' and invalid_reason='OK' do not get marked invalid."""
        mock_records = [
            {
                "file_name": "resume1.pdf",
                "parsed_text": "A" * 300,
                "pages": 1,
                "status": "valid",
                "invalid_reason": "OK",
            }
        ]
        self.dm.db_handler.fetch_resume_files.return_value = mock_records
        res = self.dm.process_all_resumes(company_id=101)

        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["status"], "valid")
        self.assertEqual(res[0]["reason"], "")

    def test_status_valid_with_pypdf_skipped_reason(self):
        """Ensures that records with status='valid' and invalid_reason='OK (pypdf check skipped)' do not get marked invalid."""
        mock_records = [
            {
                "file_name": "resume2.pdf",
                "parsed_text": "B" * 300,
                "pages": 1,
                "status": "valid",
                "invalid_reason": "OK (pypdf check skipped)",
            }
        ]
        self.dm.db_handler.fetch_resume_files.return_value = mock_records
        res = self.dm.process_all_resumes(company_id=101)

        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["status"], "valid")
        self.assertEqual(res[0]["reason"], "")

    def test_status_invalid_preserves_error(self):
        """Ensures that records with status='invalid' retain their error message."""
        mock_records = [
            {
                "file_name": "corrupt.pdf",
                "parsed_text": "",
                "pages": 0,
                "status": "invalid",
                "invalid_reason": "Corrupt or unreadable PDF: file corrupted",
            }
        ]
        self.dm.db_handler.fetch_resume_files.return_value = mock_records
        res = self.dm.process_all_resumes(company_id=101)

        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["status"], "invalid")
        self.assertIn("Corrupt", res[0]["reason"])

    def test_fetch_scoping_passed_to_handler(self):
        """Ensures company_id is forwarded to db_handler for tenant scoping."""
        self.dm.db_handler.fetch_resume_files.return_value = []
        self.dm.process_all_resumes(company_id=42)
        self.dm.db_handler.fetch_resume_files.assert_called_once_with(company_id=42)

    def test_resume_id_is_passed_through(self):
        """Ensures each resume dict keeps its database row id."""
        mock_records = [
            {
                "id": 7,
                "file_name": "resume1.pdf",
                "parsed_text": "A" * 300,
                "pages": 1,
                "status": "valid",
                "invalid_reason": "",
            }
        ]
        self.dm.db_handler.fetch_resume_files.return_value = mock_records
        res = self.dm.process_all_resumes(company_id=101)

        self.assertEqual(res[0]["id"], 7)

    def test_non_resume_job_description_and_anonymized_sample_marked_invalid(self):
        """Detects job descriptions and anonymized sample templates at Resume initialization."""
        jd = Resume(
            "IT Infrastructure Administrator Resume (Invalid example).pdf",
            raw_text="COMPANY : Acme\nJOB TITLE : IT Admin\nMAIN PURPOSE OF THE JOB\n" + ("Duties " * 40),
            pages=1,
        )
        sample = Resume(
            "Senior IT Project Manager Resume (Invalid example).pdf",
            raw_text="Resume Sample\nName & Personal Details of clients are not included for Anonymity\nE-mail: xxxxx@example.com\n" + ("Project " * 40),
            pages=1,
        )
        valid = Resume(
            "Ada_Lovelace.pdf",
            raw_text="Ada Lovelace\nSenior Software Engineer with Python, APIs, and distributed backend systems.\n" + ("Work experience details " * 15),
            pages=1,
        )

        self.assertEqual(jd.status, "invalid")
        self.assertIn("job description", jd.reason.lower())
        self.assertEqual(sample.status, "invalid")
        self.assertIn("anonymized", sample.reason.lower())
        self.assertEqual(valid.status, "valid")

    def test_upload_resume_bytes_sanitizes_name_and_updates_without_upsert(self):
        from data_manager_modules.data_manager_supabase_handler import SupabaseHandler

        handler = SupabaseHandler.__new__(SupabaseHandler)
        client = MagicMock()
        handler.client = client
        handler.STORAGE_BUCKET = "resume_files"

        bucket = MagicMock()
        bucket.get_public_url.return_value = "https://example.com/101/Ada_Lovelace.pdf"
        client.storage.from_.return_value = bucket

        table = MagicMock()
        client.table.return_value = table
        select_chain = table.select.return_value.eq.return_value.eq.return_value
        select_chain.execute.return_value = MagicMock(data=[])

        parsed = Resume("Ada_Lovelace.pdf", raw_text="Ada Lovelace\n" + ("Python engineer " * 30), pages=1)
        handler.parse_pdf_bytes = MagicMock(return_value=parsed)

        out = handler.upload_resume_bytes("Ada Lovelace.pdf", b"%PDF-1.4", company_id=101)
        self.assertEqual(out["file_name"], "Ada_Lovelace.pdf")
        table.upsert.assert_not_called()
        table.insert.assert_called_once()

        select_chain.execute.return_value = MagicMock(data=[{"id": 99}])
        handler.upload_resume_bytes("Ada Lovelace.pdf", b"%PDF-1.4", company_id=101)
        table.update.assert_called_once()

if __name__ == "__main__":
    unittest.main()

