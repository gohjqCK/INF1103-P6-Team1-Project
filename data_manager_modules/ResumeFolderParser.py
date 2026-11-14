#FOR OFFLINE USE -- Used if SUPABASE is down
from typing import Any, Dict, List

from pypdf import PdfReader

from data_manager_modules.data_manager_resume import Resume
from data_manager_modules.ResumeFolder import ResumeFolder


class ResumeFolderParser:
    """Parses local PDF files into resume dicts (the local-disk counterpart of ResumePDFParser)."""

    def parse(self, folder: str) -> List[Dict[str, Any]]:
        """Returns resume dicts, valid resumes first, invalid last. Empty list if the folder is missing."""
        resume_folder = ResumeFolder(folder)
        if not resume_folder.exists():
            print(f"  [!] Resume folder not found: '{folder}'")
            return []

        pdf_files = resume_folder.pdf_files()
        print(f"  [Parse] Found {len(pdf_files)} PDF(s) in {resume_folder.path.resolve()}")

        resumes = [self._parse_file(pdf) for pdf in pdf_files]
        valid = [r for r in resumes if r.status == "valid"]
        invalid = [r for r in resumes if r.status != "valid"]
        return [r.to_dict() for r in valid + invalid]

    @staticmethod
    def _parse_file(pdf_path) -> Resume:
        """Extracts the text of one PDF. A bad file becomes an invalid Resume instead of crashing the batch."""
        try:
            reader = PdfReader(str(pdf_path))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            return Resume(file_name=pdf_path.name, raw_text=text, pages=len(reader.pages))
        except Exception as error:
            return Resume(file_name=pdf_path.name, error_message=f"Could not read the PDF: {error}")