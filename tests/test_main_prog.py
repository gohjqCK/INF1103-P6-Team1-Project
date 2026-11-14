import shutil
import tempfile
import unittest
from pathlib import Path

from main_modules.MainProg import MainProg


class TestMainProgAuditFixes(unittest.TestCase):
    def test_generate_overview_report_handles_summary_dict_shapes(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            prog = MainProg(output_dir=tmp_dir)
            report_path = prog.generate_overview_report(
                {
                    "top_candidates": [
                        {
                            "name": "Ada Lovelace",
                            "file": "ada.pdf",
                            "score": 92.5,
                            "outcome": "scored",
                            "reason": "Meets all rules.",
                        }
                    ]
                }
            )
            text = Path(report_path).read_text(encoding="utf-8")
            self.assertIn("Ada Lovelace", text)
            self.assertIn("92.5", text)

            shortlisted_path = prog.generate_overview_report(
                {
                    "shortlisted": [
                        {
                            "name": "Grace Hopper",
                            "file": "grace.pdf",
                            "score": 98.0,
                            "reason": "Compiler pioneer.",
                        }
                    ]
                }
            )
            self.assertIn("Grace Hopper", Path(shortlisted_path).read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
