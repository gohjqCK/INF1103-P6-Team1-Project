"""Encapsulates formatting and rendering of candidate results and profile cards."""
from datetime import datetime, timezone, timedelta
import glob
import json
import os
from typing import Any, Dict, List, Optional

from io_manager_modules.io_manager_input_validator import InputValidator


class ResultPresenter:
    """Formats screening rankings, full candidate profile cards, and saved JSON views."""

    def __init__(self, validator: Optional[InputValidator] = None):
        # SGT = UTC+8
        self._sgt_timezone = timezone(timedelta(hours=8))
        self._validator = validator or InputValidator()

    @staticmethod
    def get_candidate_sort_score(candidate: Any) -> float:
        """Safely extracts candidate score as a float for sorting."""
        if isinstance(candidate, dict):
            val = candidate.get("score")
        elif hasattr(candidate, "score"):
            val = candidate.score
        else:
            return -1.0

        if val is None:
            return -1.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return -1.0

    def display_screening_results(
        self, ranked_candidates: List[Any], top_n: Optional[int] = None
    ) -> List[Any]:
        """Renders candidate records cleanly, guarding against missing keys or invalid types."""
        if not isinstance(ranked_candidates, list) or not ranked_candidates:
            print("\n  [i] No candidate results available to display.")
            return []

        if isinstance(ranked_candidates[0], dict) and "accepted" in ranked_candidates[0]:
            display_list = ranked_candidates[0]["accepted"]
        else:
            display_list = ranked_candidates

        valid_candidates = [
            c for c in display_list if isinstance(c, dict) or hasattr(c, "file")
        ]
        if not valid_candidates:
            print("\n  [i] No candidate results available to display.")
            return []

        # Ensure descending score order
        valid_candidates.sort(key=self.get_candidate_sort_score, reverse=True)

        if top_n is not None and top_n > 0:
            valid_candidates = valid_candidates[:top_n]

        print("\n" + "=" * 75)
        print("                       TOP RANKED CANDIDATES")
        print("=" * 75)

        for idx, candidate in enumerate(valid_candidates, start=1):
            if isinstance(candidate, dict):
                rank = candidate.get("rank", idx)
                name = candidate.get("name") or candidate.get("file") or "Unknown Candidate"
                raw_score = candidate.get("score")
                reason = candidate.get("reason", "No evaluation summary provided.")
                outcome = candidate.get("outcome", "disqualified")
            else:
                rank = getattr(candidate, "rank", idx) or idx
                name = getattr(candidate, "name", "") or getattr(candidate, "file", "Unknown Candidate")
                raw_score = getattr(candidate, "score", None)
                reason = getattr(candidate, "reason", "No evaluation summary provided.")
                outcome = getattr(candidate, "outcome", "disqualified")

            if raw_score is not None:
                try:
                    score_str = f"{float(raw_score):.1f}%"
                except (ValueError, TypeError):
                    score_str = str(raw_score)
            else:
                score_str = f"N/A ({outcome})"

            print(f"\n  [Rank #{rank}]  {str(name).strip()}")
            print(f"      Score  : {score_str}")
            print(f"      Reason : {reason}")

        print("\n" + "-" * 75)
        print("  [*] Note: Complete details saved to JSON output file")
        print("=" * 75 + "\n")

        return valid_candidates

    def display_candidate_full_details(self, candidate: Any, rank: int) -> None:
        """Displays detailed candidate profile including contact info, summaries, and lists."""
        cand_dict = candidate if isinstance(candidate, dict) else (
            candidate.to_dict() if hasattr(candidate, "to_dict") else vars(candidate)
        )

        name = cand_dict.get("name") or cand_dict.get("file") or "Unknown Candidate"
        file_name = cand_dict.get("file") or "N/A"
        email = cand_dict.get("email") or "Not provided"
        phone = cand_dict.get("phone") or "Not provided"

        raw_score = cand_dict.get("score")
        outcome = cand_dict.get("outcome") or "scored"
        if raw_score is not None:
            try:
                score_str = f"{float(raw_score):.1f}%"
            except (ValueError, TypeError):
                score_str = str(raw_score)
        else:
            score_str = f"N/A ({outcome})"

        reason = cand_dict.get("reason") or "No evaluation summary provided."
        summary = cand_dict.get("summary") or "No summary provided."

        print("\n" + "=" * 75)
        print(f"               FULL CANDIDATE PROFILE [Rank #{rank}]")
        print("=" * 75)
        print(f"  Name               : {str(name).strip()}")
        print(f"  Resume File        : {file_name}")
        print(f"  Email              : {email}")
        print(f"  Phone              : {phone}")
        print(f"  Evaluation Score   : {score_str} ({outcome})")
        print(f"  Evaluation Reason  : {reason}")
        print("-" * 75)
        print("  Candidate Summary  :")
        print(f"    {summary}")
        print("-" * 75)

        sections = [
            ("Skills", cand_dict.get("skills")),
            ("Qualifications", cand_dict.get("qualifications")),
            ("Work Experience", cand_dict.get("work_experience")),
            ("Projects", cand_dict.get("projects")),
        ]

        for section_title, section_items in sections:
            print(f"  {section_title}:")
            if isinstance(section_items, list) and section_items:
                for item in section_items:
                    print(f"    - {str(item).strip()}")
            elif isinstance(section_items, str) and section_items.strip():
                print(f"    - {section_items.strip()}")
            else:
                print("    - None listed")
            print()

        print("=" * 75 + "\n")

    def prompt_candidate_inspection(self, candidates: List[Any]) -> None:
        """Interactively prompts user to select a candidate by rank to view full profile."""
        if not candidates:
            return

        max_rank = len(candidates)
        while True:
            print(f"\nEnter candidate rank to view full details (1-{max_rank}), or '0' to return to menu:")
            choice = self._validator.safe_input("Select rank: ").strip()

            if choice == "0":
                print("Returning to main menu...\n")
                break

            if choice.isdigit():
                selected_rank = int(choice)
                if 1 <= selected_rank <= max_rank:
                    selected_candidate = candidates[selected_rank - 1]
                    self.display_candidate_full_details(selected_candidate, selected_rank)
                    continue

            print(f"\n  [!] ERROR: Invalid rank. Please enter a number between 1 and {max_rank} (or '0' to return).\n")

    def find_results_files_in_folder(self, output_dir: str = "output") -> List[str]:
        """Returns all result JSON files from output folder, sorted newest first."""
        if not os.path.exists(output_dir) or not os.path.isdir(output_dir):
            return []

        pattern = os.path.join(output_dir, "*.json")
        result_files = [
            f for f in glob.glob(pattern)
            if os.path.basename(f).lower() != "resumes.json"
        ]

        try:
            result_files.sort(key=os.path.getmtime, reverse=True)
        except OSError:
            pass

        return result_files

    def select_result_file_to_view(self, output_dir: str = "output") -> Optional[str]:
        """Displays available screening result files and prompts user to pick one."""
        files = self.find_results_files_in_folder(output_dir)

        if not files:
            root_candidates = [
                f for f in glob.glob("filtered_resume_*.json") + glob.glob("results.json")
                if os.path.isfile(f)
            ]
            if root_candidates:
                try:
                    root_candidates.sort(key=os.path.getmtime, reverse=True)
                except OSError:
                    pass
                files = root_candidates

        if not files:
            print(f"\n  [!] ERROR: No results JSON files found in '{output_dir}'. Please run screening first.\n")
            return None

        if len(files) == 1:
            print(f"\n  [*] Found 1 result file: '{os.path.basename(files[0])}'")
            return files[0]

        print("\n---------------- AVAILABLE SCREENING RESULTS ----------------")
        print(f"  Target Folder: '{output_dir}'")
        for idx, filepath in enumerate(files, start=1):
            filename = os.path.basename(filepath)
            try:
                mtime = os.path.getmtime(filepath)
                time_str = datetime.fromtimestamp(mtime, tz=timezone.utc).astimezone(self._sgt_timezone).strftime("%Y-%m-%d %H:%M:%S")
                size_kb = round(os.path.getsize(filepath) / 1024, 1)
                print(f"  {idx}. {filename}  [{time_str} SGT | {size_kb} KB]")
            except OSError:
                print(f"  {idx}. {filename}")
        print("-------------------------------------------------------------")

        print("\nEnter result number to view (or '0' to cancel):")
        valid_choices = [str(i) for i in range(len(files) + 1)]
        choice = self._validator.get_valid_menu_choice(valid_choices)

        if choice == "0":
            print("View results cancelled.")
            return None

        return files[int(choice) - 1]

    def view_saved_results(
        self, file_path: Optional[str] = None, top_n: Optional[int] = None, output_dir: str = "output"
    ) -> None:
        """Reads and parses saved JSON output with protection against corruption."""
        target = file_path or self.select_result_file_to_view(output_dir)
        if not target:
            return

        try:
            if os.path.getsize(target) == 0:
                print(f"\n  [!] ERROR: '{target}' is empty. Re-run screening to generate output.\n")
                return
        except OSError as err:
            print(f"\n  [!] ERROR: Failed to check file size for '{target}': {err}\n")
            return

        print(f"\n  [i] Reading results from '{target}'...")
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                print(f"\n  [!] ERROR: '{target}' contains invalid data structure (expected JSON array).\n")
                return

            displayed_candidates = self.display_screening_results(data, top_n=top_n)
            if displayed_candidates:
                self.prompt_candidate_inspection(displayed_candidates)

        except json.JSONDecodeError as err:
            print(f"\n  [!] ERROR: Corrupted JSON in '{target}': {err.msg} (line {err.lineno})\n")
        except PermissionError:
            print(f"\n  [!] ERROR: Permission denied reading '{target}'.\n")
        except Exception as err:
            print(f"\n  [!] ERROR: Unexpected error while opening '{target}': {err}\n")

    def display_summary_report(self, summary_file: str = "summary.json") -> None:
        """Displays formatted AI Summary Report (totals, scores, rule statistics, narrative)."""
        if not os.path.exists(summary_file) or os.path.getsize(summary_file) == 0:
            print(f"\n  [!] ERROR: Summary report file '{summary_file}' not found or empty.")
            print("      Please run AI Screening from Option 4 first to generate the summary report.\n")
            return

        try:
            with open(summary_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            totals = data.get("totals", {})
            scores = data.get("score_statistics") or data.get("scores", {})
            rules = data.get("rule_statistics") or data.get("rules", [])
            top_candidates = data.get("top_candidates", [])
            overall_summary = data.get("overall_summary", "No AI narrative available.")
            invalid_docs = data.get("invalid_documents", [])

            print("\n" + "=" * 75)
            print("                       AI SCREENING SUMMARY REPORT")
            print("=" * 75)

            print("\n  1. EXECUTIVE AI NARRATIVE:")
            print(f"     {overall_summary}\n")

            total_resumes = totals.get("processed", totals.get("resumes", 0))
            print("  2. APPLICANT POOL BREAKDOWN:")
            print(f"     • Total Resumes Evaluated : {total_resumes}")
            print(f"     • Qualifying / Scored     : {totals.get('scored', 0)}")
            print(f"     • Disqualified / Rejected : {totals.get('rejected', 0)}")
            print(f"     • Invalid / Unreadable    : {totals.get('invalid', 0)}")

            avg_val = scores.get("average")
            high_val = scores.get("highest")
            low_val = scores.get("lowest")
            med_val = scores.get("median")
            avg_s = f"{float(avg_val):.1f}%" if avg_val is not None else "N/A"
            high_s = f"{float(high_val):.1f}%" if high_val is not None else "N/A"
            low_s = f"{float(low_val):.1f}%" if low_val is not None else "N/A"
            med_s = f"{float(med_val):.1f}%" if med_val is not None else "N/A"

            print("\n  3. SCORE METRICS (SCORED POOL):")
            print(f"     • Average: {avg_s}  |  Median: {med_s}  |  Highest: {high_s}  |  Lowest: {low_s}")

            print("\n  4. TOP SHORTLISTED CANDIDATES:")
            if top_candidates:
                for idx, c in enumerate(top_candidates, 1):
                    rank = c.get("rank", idx)
                    name = c.get("name") or c.get("file") or f"Candidate #{rank}"
                    c_score = c.get("score")
                    sc_s = f"{float(c_score):.1f}%" if c_score is not None else "N/A"
                    met_rules = ", ".join(c.get("rules_met", [])) or "None"
                    print(f"     [Rank #{rank}] {name} (Score: {sc_s})")
                    print(f"          Rules Met: {met_rules}")
            else:
                print("     • No qualifying candidates recorded.")

            print("\n  5. PER-RULE MATCH BREAKDOWN:")
            if rules:
                for idx, r in enumerate(rules, 1):
                    prio = str(r.get("priority", "rule")).upper()
                    text = r.get("rule") or r.get("text", "")
                    met = r.get("met") if "met" in r else r.get("met_count", 0)
                    if "missed" in r:
                        checked = met + r.get("missed", 0)
                    else:
                        checked = r.get("checked_count", 0)
                    rate = r.get("percent_met") if "percent_met" in r else r.get("met_rate", 0.0)
                    chk_str = f"/{checked}" if checked else ""
                    print(f"     {idx}. [{prio}] {text}")
                    print(f"        Matched: {met}{chk_str} ({float(rate):.1f}%)")
            else:
                print("     • No rule statistics recorded.")

            if invalid_docs:
                print("\n  6. INVALID / UNREADABLE RESUMES:")
                for inv in invalid_docs:
                    print(f"     • {inv.get('file', 'Unknown')}: {inv.get('reason', 'N/A')}")

            print("\n" + "=" * 75 + "\n")

        except json.JSONDecodeError as err:
            print(f"\n  [!] ERROR: Corrupted JSON in '{summary_file}': {err}\n")
        except Exception as err:
            print(f"\n  [!] ERROR: Could not read summary report: {err}\n")
