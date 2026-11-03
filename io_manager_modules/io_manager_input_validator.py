"""Encapsulates terminal input validation and file-system directory checking."""
import os
import sys
from typing import List, Optional, Tuple


class InputValidator:
    """Handles safe user input, menu selection guards, and directory scanning."""

    def __init__(self):
        self._priority_map = {
            "1": "must",
            "2": "important",
            "3": "nice",
            "4": "can consider",
        }

    def safe_input(self, prompt_text: str = "") -> str:
        """Intercepts KeyboardInterrupt and EOFError to exit gracefully."""
        try:
            return input(prompt_text)
        except (KeyboardInterrupt, EOFError):
            print("\n\n[!] Session interrupted by user. Exiting safely...")
            sys.exit(0)

    def get_valid_menu_choice(self, allowed_choices: List[str]) -> str:
        """Validates user choice against an explicit list of allowed strings."""
        while True:
            choice = self.safe_input(f"Select an option ({'/'.join(allowed_choices)}): ").strip()
            if choice in allowed_choices:
                return choice
            print(f"\n  [!] ERROR: Invalid selection. Expected one of: {', '.join(allowed_choices)}\n")

    def get_valid_priority(self) -> str:
        """Prompts for rule priority weight. Defaults to 'reject' if left blank."""
        print("  Select priority weight:")
        print("    1. Must (Weight: 4)")
        print("    2. Important (Weight: 3)")
        print("    3. Nice (Weight: 2)")
        print("    4. Can consider (Weight: 1)")
        print("    5. No weight (Sets priority to 'reject')")

        while True:
            choice = self.safe_input("Enter priority (1-4, or press Enter / 5 for reject): ").strip()
            if choice in ["", "5"]:
                print("  [*] No weight provided. Setting priority to 'reject'.")
                return "reject"
            if choice in self._priority_map:
                return self._priority_map[choice]

            print("\n  [!] ERROR: Invalid choice. Select 1-4, or press Enter / 5 for reject.\n")

    def scan_pdf_count(self, folder_path: str) -> Tuple[bool, int, str]:
        """Safely checks a folder and counts PDF files inside.

        Returns: (is_accessible, pdf_count, error_message)
        """
        if not os.path.exists(folder_path):
            return False, 0, f"Path '{folder_path}' does not exist."
        if not os.path.isdir(folder_path):
            return False, 0, f"Path '{folder_path}' is a file, not a directory."

        try:
            entries = os.listdir(folder_path)
        except PermissionError:
            return False, 0, f"Permission denied accessing '{folder_path}'."
        except OSError as err:
            return False, 0, f"Operating system error reading '{folder_path}': {err}"

        pdf_files = [f for f in entries if f.lower().endswith(".pdf")]
        return True, len(pdf_files), ""

    def get_valid_pdf_directory(self) -> str:
        """Validates host resume directories against path and permission errors."""
        print("\n--- STEP 1: RESUME FOLDER SELECTION ---")
        print("Tip: Press ENTER to use the default 'resumes' directory.\n")

        while True:
            folder_path = self.safe_input("Enter directory path [Default: resumes]: ").strip()
            if not folder_path:
                folder_path = "resumes"

            folder_path = folder_path.strip("'\"").replace("\\ ", " ")
            is_valid, pdf_count, err_msg = self.scan_pdf_count(folder_path)

            if not is_valid:
                print(f"\n  [!] ERROR: {err_msg}\n")
                continue
            if pdf_count == 0:
                print(f"\n  [!] ERROR: No PDF files (.pdf) found in '{folder_path}'.\n")
                continue

            print(f"  [+] SUCCESS: Found {pdf_count} PDF resume(s) in '{folder_path}'.")
            return folder_path

    def get_valid_top_n_candidates(self, max_available: Optional[int] = None) -> int:
        """Validates top N input against non-integers, zeros, and upper boundaries."""
        print("\n--- STEP 2: CANDIDATE OUTPUT LIMIT ---")
        while True:
            raw_val = self.safe_input("How many top candidates to return (e.g., 3, 5)? ").strip()
            if not raw_val.isdigit():
                print("\n  [!] ERROR: Invalid input. Please enter a positive integer.\n")
                continue

            count = int(raw_val)
            if count <= 0:
                print("\n  [!] ERROR: Limit must be at least 1.\n")
                continue

            if max_available and count > max_available:
                print(f"  [*] Notice: Only {max_available} PDF(s) available. Capping limit to {max_available}.")
                return max_available

            return count

    def configure_resumes_and_limit(self) -> Tuple[str, int]:
        """Coordinates directory and candidate limit selection."""
        folder = self.get_valid_pdf_directory()
        _, pdf_count, _ = self.scan_pdf_count(folder)
        limit = self.get_valid_top_n_candidates(max_available=pdf_count)
        print(f"  [+] SUCCESS: Configured folder '{folder}' with candidate limit of {limit}.")
        return folder, limit

    def get_valid_output_directory(self, current_output_dir: str = "output") -> str:
        """Validates and configures the directory where screening result JSON files are stored."""
        print("\n--- STEP: OUTPUT RESULTS FOLDER SELECTION ---")
        print(f"Tip: Press ENTER to use the current/default folder '{current_output_dir}'.\n")

        while True:
            folder_path = self.safe_input(f"Enter output directory path [Default: {current_output_dir}]: ").strip()
            if not folder_path:
                folder_path = current_output_dir

            folder_path = folder_path.strip("'\"").replace("\\ ", " ")

            try:
                os.makedirs(folder_path, exist_ok=True)
                test_file = os.path.join(folder_path, ".write_test.tmp")
                with open(test_file, "w") as f:
                    f.write("ok")
                os.remove(test_file)
            except PermissionError:
                print(f"\n  [!] ERROR: Permission denied accessing or creating folder '{folder_path}'.\n")
                continue
            except OSError as err:
                print(f"\n  [!] ERROR: Operating system error for folder '{folder_path}': {err}\n")
                continue

            print(f"  [+] SUCCESS: Output folder configured: '{folder_path}'.")
            return folder_path