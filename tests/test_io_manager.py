"""Unit tests for I/O Manager components (CLI, Validator, Presenter, Telegram Formatter/Keyboards).
All tests run offline without network access or live API tokens.
"""
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from io_manager_modules.io_manager_base import BaseIOManager
from io_manager_modules.io_manager_cli import CLIIOManager
from io_manager_modules.io_manager_input_validator import InputValidator
from io_manager_modules.io_manager_result_presenter import ResultPresenter
from io_manager_modules.io_manager_rule_handler import RuleInputHandler
from io_manager_modules.telegram_formatter import TelegramFormatter
from io_manager_modules.telegram_keyboards import TelegramKeyboards


class TestInputValidator(unittest.TestCase):
    """Verifies user input validation, priority mappings, and directory checking."""

    def setUp(self):
        self.validator = InputValidator()
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch("builtins.input", side_effect=["2"])
    def test_get_valid_menu_choice_accepts_valid_option(self, mock_input):
        choice = self.validator.get_valid_menu_choice(["1", "2", "3"])
        self.assertEqual(choice, "2")

    @patch("builtins.input", side_effect=["invalid", "99", "1"])
    def test_get_valid_menu_choice_retries_on_invalid_option(self, mock_input):
        choice = self.validator.get_valid_menu_choice(["1", "2"])
        self.assertEqual(choice, "1")

    @patch("builtins.input", side_effect=["1"])
    def test_get_valid_priority_must(self, mock_input):
        self.assertEqual(self.validator.get_valid_priority(), "must")

    @patch("builtins.input", side_effect=["2"])
    def test_get_valid_priority_important(self, mock_input):
        self.assertEqual(self.validator.get_valid_priority(), "important")

    @patch("builtins.input", side_effect=["3"])
    def test_get_valid_priority_nice(self, mock_input):
        self.assertEqual(self.validator.get_valid_priority(), "nice")

    @patch("builtins.input", side_effect=["4"])
    def test_get_valid_priority_can_consider(self, mock_input):
        self.assertEqual(self.validator.get_valid_priority(), "can consider")

    @patch("builtins.input", side_effect=[""])
    def test_get_valid_priority_defaults_to_reject_on_empty(self, mock_input):
        self.assertEqual(self.validator.get_valid_priority(), "reject")

    @patch("builtins.input", side_effect=["5"])
    def test_get_valid_priority_reject_on_choice_five(self, mock_input):
        self.assertEqual(self.validator.get_valid_priority(), "reject")

    def test_scan_pdf_count_counts_only_pdfs(self):
        (Path(self.test_dir) / "doc1.pdf").write_text("dummy")
        (Path(self.test_dir) / "doc2.PDF").write_text("dummy")
        (Path(self.test_dir) / "notes.txt").write_text("dummy")
        (Path(self.test_dir) / "image.png").write_text("dummy")

        is_valid, count, err = self.validator.scan_pdf_count(self.test_dir)
        self.assertTrue(is_valid)
        self.assertEqual(count, 2)
        self.assertEqual(err, "")

    def test_scan_pdf_count_nonexistent_directory(self):
        fake_path = os.path.join(self.test_dir, "does_not_exist")
        is_valid, count, err = self.validator.scan_pdf_count(fake_path)
        self.assertFalse(is_valid)
        self.assertEqual(count, 0)
        self.assertIn("does not exist", err)

    @patch("builtins.input", side_effect=["abc", "-1", "0", "4"])
    def test_get_valid_top_n_candidates_retries_and_accepts_positive(self, mock_input):
        limit = self.validator.get_valid_top_n_candidates(max_available=10)
        self.assertEqual(limit, 4)

    @patch("builtins.input", side_effect=["10"])
    def test_get_valid_top_n_candidates_caps_to_max_available(self, mock_input):
        limit = self.validator.get_valid_top_n_candidates(max_available=3)
        self.assertEqual(limit, 3)


class TestResultPresenter(unittest.TestCase):
    """Verifies candidate scoring sorting, profile formatting, and report output."""

    def setUp(self):
        self.presenter = ResultPresenter()
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_get_candidate_sort_score_dict(self):
        self.assertEqual(ResultPresenter.get_candidate_sort_score({"score": 85.5}), 85.5)
        self.assertEqual(ResultPresenter.get_candidate_sort_score({"score": "92.0"}), 92.0)
        self.assertEqual(ResultPresenter.get_candidate_sort_score({"score": None}), -1.0)
        self.assertEqual(ResultPresenter.get_candidate_sort_score({}), -1.0)

    def test_get_candidate_sort_score_object(self):
        class DummyCand:
            def __init__(self, score):
                self.score = score

        self.assertEqual(ResultPresenter.get_candidate_sort_score(DummyCand(77.0)), 77.0)
        self.assertEqual(ResultPresenter.get_candidate_sort_score(DummyCand(None)), -1.0)

    def test_display_screening_results_sorts_descending(self):
        candidates = [
            {"name": "Alice", "file": "alice.pdf", "score": 60.0, "reason": "OK"},
            {"name": "Bob", "file": "bob.pdf", "score": 95.0, "reason": "Great"},
            {"name": "Charlie", "file": "charlie.pdf", "score": 80.0, "reason": "Good"},
        ]
        with patch("sys.stdout", new=io.StringIO()):
            sorted_res = self.presenter.display_screening_results(candidates, top_n=3)

        self.assertEqual(len(sorted_res), 3)
        self.assertEqual(sorted_res[0]["name"], "Bob")
        self.assertEqual(sorted_res[1]["name"], "Charlie")
        self.assertEqual(sorted_res[2]["name"], "Alice")

    def test_display_screening_results_caps_top_n(self):
        candidates = [
            {"name": f"Cand {i}", "file": f"c{i}.pdf", "score": float(i * 10)}
            for i in range(1, 6)
        ]
        with patch("sys.stdout", new=io.StringIO()):
            sorted_res = self.presenter.display_screening_results(candidates, top_n=2)

        self.assertEqual(len(sorted_res), 2)
        self.assertEqual(sorted_res[0]["score"], 50.0)
        self.assertEqual(sorted_res[1]["score"], 40.0)

    def test_display_candidate_full_details_handles_sparse_candidate(self):
        sparse_cand = {"name": "Jordan", "file": "jordan.pdf"}
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            self.presenter.display_candidate_full_details(sparse_cand, rank=1)
            output = fake_out.getvalue()

        self.assertIn("Jordan", output)
        self.assertIn("jordan.pdf", output)
        self.assertIn("None listed", output)

    def test_display_summary_report_renders_sections(self):
        summary_path = os.path.join(self.test_dir, "summary.json")
        sample_report = {
            "totals": {"processed": 4, "scored": 3, "rejected": 1, "invalid": 0},
            "score_statistics": {"average": 82.5, "median": 85.0, "highest": 95.0, "lowest": 70.0},
            "rule_statistics": [
                {"rule": "Python experience", "priority": "must", "met": 3, "missed": 1, "percent_met": 75.0}
            ],
            "top_candidates": [
                {"rank": 1, "name": "Bob", "file": "bob.pdf", "score": 95.0, "rules_met": ["Python experience"]}
            ],
            "overall_summary": "Strong candidate pool with high Python proficiency.",
        }
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(sample_report, f)

        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            self.presenter.display_summary_report(summary_file=summary_path)
            output = fake_out.getvalue()

        self.assertIn("AI SCREENING SUMMARY REPORT", output)
        self.assertIn("Strong candidate pool", output)
        self.assertIn("Total Resumes Evaluated : 4", output)
        self.assertIn("Average: 82.5%", output)
        self.assertIn("Bob (Score: 95.0%)", output)
        self.assertIn("Python experience", output)


class TestRuleInputHandler(unittest.TestCase):
    """Verifies adding, viewing, and clearing business rules."""

    def setUp(self):
        self.handler = RuleInputHandler(InputValidator())

    @patch("builtins.input", side_effect=["5"])
    def test_manage_business_rules_exit_without_modifications(self, mock_input):
        rules = [{"text": "Knows Python", "priority": "must"}]
        with patch("sys.stdout", new=io.StringIO()):
            out_rules = self.handler.manage_business_rules(rules)
        self.assertEqual(len(out_rules), 1)
        self.assertEqual(out_rules[0]["text"], "Knows Python")

    @patch("builtins.input", side_effect=["2", "Must have 3+ years in cloud computing", "1", "n", "5"])
    def test_add_rule_successfully(self, mock_input):
        rules = []
        with patch("sys.stdout", new=io.StringIO()):
            out_rules = self.handler.manage_business_rules(rules)
        self.assertEqual(len(out_rules), 1)
        self.assertEqual(out_rules[0]["text"], "Must have 3+ years in cloud computing")
        self.assertEqual(out_rules[0]["priority"], "must")

    @patch("builtins.input", side_effect=["3", "1", "5"])
    def test_delete_rule_by_index(self, mock_input):
        rules = [
            {"text": "First rule to delete", "priority": "must"},
            {"text": "Second rule to keep", "priority": "nice"},
        ]
        with patch("sys.stdout", new=io.StringIO()):
            out_rules = self.handler.manage_business_rules(rules)
        self.assertEqual(len(out_rules), 1)
        self.assertEqual(out_rules[0]["text"], "Second rule to keep")


class TestTelegramFormatterAndKeyboards(unittest.TestCase):
    """Verifies Telegram Bot card formatting and inline keyboard generation."""

    def test_format_dashboard_contains_company_metadata(self):
        text = TelegramFormatter.format_dashboard(
            company_name="Acme Corp",
            invite_code="ACME-1234",
            company_id=101,
            resume_count=5,
        )
        self.assertIn("Acme Corp", text)
        self.assertIn("ACME-1234", text)
        self.assertIn("#101", text)
        self.assertIn("5 PDF(s)", text)

    def test_format_results_overview(self):
        ranked = [
            {"name": "Alice", "score": 90.5, "reason": "Strong match"},
            {"name": "Bob", "score": 80.0, "reason": "Good match"},
        ]
        text = TelegramFormatter.format_results_overview("Acme Corp", ranked)
        self.assertIn("Alice", text)
        self.assertIn("90.5%", text)
        self.assertIn("Bob", text)
        self.assertIn("80.0%", text)

    def test_format_ai_summary_json_renders_all_fields(self):
        summary_data = {
            "totals": {"processed": 5, "scored": 4, "rejected": 1, "invalid": 0},
            "score_statistics": {"average": 85.0, "highest": 95.0, "lowest": 75.0},
            "rule_statistics": [
                {"rule": "Must know SQL", "priority": "must", "met": 4, "missed": 0, "percent_met": 100.0}
            ],
            "top_candidates": [
                {"rank": 1, "name": "Alice", "score": 95.0, "reason": "Matched all rules"}
            ],
            "overall_summary": "Excellent talent pool.",
        }
        text = TelegramFormatter.format_ai_summary_json("Acme Corp", summary_data)
        self.assertIn("RESUM-AI SUMMARY REPORT (Acme Corp)", text)
        self.assertIn("Excellent talent pool.", text)
        self.assertIn("Total Resumes: <b>5</b>", text)
        self.assertIn("Must know SQL", text)
        self.assertIn("Alice", text)

    def test_keyboards_generate_valid_markups(self):
        auth_kb = TelegramKeyboards.auth_menu()
        self.assertIsNotNone(auth_kb.keyboard)
        self.assertEqual(len(auth_kb.keyboard), 2)

        dash_kb = TelegramKeyboards.dashboard_menu()
        self.assertIsNotNone(dash_kb.keyboard)
        self.assertGreaterEqual(len(dash_kb.keyboard), 4)

        results_kb = TelegramKeyboards.results_menu(ranked_count=3)
        self.assertIsNotNone(results_kb.keyboard)


class TestCLIIOManager(unittest.TestCase):
    """Verifies that CLIIOManager implements BaseIOManager and handles company files."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.companies_file = os.path.join(self.test_dir, "test_companies.json")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_cli_io_manager_implements_base_interface(self):
        self.assertTrue(issubclass(CLIIOManager, BaseIOManager))
        cli = CLIIOManager(data_file=self.companies_file)
        self.assertIsInstance(cli, BaseIOManager)

    def test_display_methods_run_without_errors(self):
        cli = CLIIOManager(data_file=self.companies_file)
        with patch("sys.stdout", new=io.StringIO()):
            cli.display_message("Test message")
            cli.display_error("Test error")
            cli.display_success("Test success")
            res = cli.display_screening_results([{"file": "test.pdf", "score": 80.0}])
            self.assertEqual(len(res), 1)

    def test_load_and_save_companies_assigns_ids(self):
        initial_data = {
            "Old Company": {
                "owner": 12345,
                "invite_code": "OLD-1234",
                "passcode_hash": "hash123",
                "members": [12345],
            }
        }
        with open(self.companies_file, "w", encoding="utf-8") as f:
            json.dump(initial_data, f)

        cli = CLIIOManager(data_file=self.companies_file)
        companies = cli._load_companies()

        self.assertIn("Old Company", companies)
        self.assertIn("company_id", companies["Old Company"])
        self.assertEqual(companies["Old Company"]["company_id"], 101)


if __name__ == "__main__":
    unittest.main()
