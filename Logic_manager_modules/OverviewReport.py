import os
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime


class LogicReportGenerator:
    """Generates a short overview text report from candidate evaluation results."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_field(self, candidate: Dict[str, Any], keys: List[str], default: Any = "N/A") -> Any:
        for key in keys:
            if key in candidate and candidate[key] is not None:
                return candidate[key]
        return default

    def generate_overview_report(
        self, 
        candidates: List[Dict[str, Any]], 
        filename: str = "screening_overview.txt"
    ) -> Path:
        """Generates a clean, short overview report of evaluated candidates."""
        file_path = self.output_dir / filename
        
        lines = [
            "==================================================",
            "         CANDIDATE SCREENING OVERVIEW REPORT      ",
            "==================================================",
            f"Generated At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total Processed: {len(candidates)} candidate(s)",
            "--------------------------------------------------\n"
        ]
        
        for rank, c in enumerate(candidates, start=1):
            name = self._get_field(c, ["candidate_name", "name", "file_name", "filename"], "Unknown")
            score = self._get_field(c, ["score", "total_score", "evaluation_score"], 0)
            status = self._get_field(c, ["status", "outcome", "decision"], "Evaluated")
            summary = self._get_field(c, ["reason", "summary", "evaluation_summary", "feedback"], "N/A")
            
            if isinstance(summary, list):
                summary = "; ".join(map(str, summary))
            
            lines.append(f"Rank {rank}: {name}")
            lines.append(f"  - Status: {status} | Score: {score}")
            lines.append(f"  - Summary: {str(summary).strip()}")
            lines.append("")

        lines.append("==================================================")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"  [+] Overview report saved to: {file_path}")
        return file_path