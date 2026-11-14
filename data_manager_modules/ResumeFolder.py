#FOR OFFLINE USE -- Used if SUPABASE is down
from pathlib import Path
from typing import List


class ResumeFolder:
    """A folder of resume PDFs on disk."""

    # The project root (the folder that holds main.py and data_manager_modules/)
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

    def __init__(self, folder: str):
        self.requested = folder
        self.path = self._resolve(folder)

    @classmethod
    def _resolve(cls, folder: str) -> Path:
        """Looks in the current directory first, then in the project folder."""
        path = Path(folder).expanduser()
        if path.is_dir():
            return path
        in_project = cls.PROJECT_ROOT / folder
        return in_project if in_project.is_dir() else path

    def exists(self) -> bool:
        return self.path.is_dir()

    def pdf_files(self) -> List[Path]:
        """Every PDF in the folder, sorted by name. Matches .pdf and .PDF."""
        if not self.exists():
            return []
        return sorted(p for p in self.path.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")