"""Streams remote PDF files in memory and parses text using pypdf."""
import io
import logging
import urllib.request
from typing import Optional
from pypdf import PdfReader
from data_manager_modules.data_manager_resume import Resume

logging.getLogger("pypdf").setLevel(logging.CRITICAL)


class ResumePDFParser:
    """Streams and parses PDF documents into structural text."""

    @staticmethod
    def parse_from_url(file_name: str, pdf_url: Optional[str]) -> Resume:
        """Downloads a PDF stream into memory and extracts text."""
        if not pdf_url:
            return Resume(file_name=file_name, error_message="No valid pdf_url found in database entry.")

        text = ""
        pages = 0
        try:
            req = urllib.request.Request(pdf_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response_stream:
                pdf_bytes = response_stream.read()

            reader = PdfReader(io.BytesIO(pdf_bytes))
            pages = len(reader.pages)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
            return Resume(file_name=file_name, raw_text=text, pages=pages)
        except Exception as error:
            return Resume(file_name=file_name, error_message=f"Could not read the PDF stream: {error}")