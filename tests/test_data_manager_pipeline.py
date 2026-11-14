import unittest
from unittest.mock import MagicMock
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

if __name__ == "__main__":
    unittest.main()

