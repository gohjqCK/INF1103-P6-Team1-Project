from datetime import datetime, timezone, timedelta
import glob
import json
import os
import sys

# Singapore Standard Time (SGT = UTC+8)
SGT_TIMEZONE = timezone(timedelta(hours=8))

# =====================================================================
# DISPLAY HELPERS
# =====================================================================


def display_message(message: str) -> None:
    """Prints standard CLI information."""
    print(message)


def display_error(error_message: str) -> None:
    """Prints highlighted error notifications."""
    print(f"\n  [!] ERROR: {error_message}\n")


def display_success(success_message: str) -> None:
    """Prints highlighted confirmation notifications."""
    print(f"  [+] SUCCESS: {success_message}")


# =====================================================================
# SAFE INPUT & SELECTION HELPERS
# =====================================================================


def safe_input(prompt_text: str = "") -> str:
    """Wraps built-in input() to intercept Ctrl+C and Ctrl+D.

    Ensures the CLI shuts down cleanly instead of printing a raw traceback.
    """
    try:
        return input(prompt_text)
    except (KeyboardInterrupt, EOFError):
        print("\n\n[!] Session interrupted by user. Exiting safely...")
        sys.exit(0)


def get_valid_menu_choice(allowed_choices: list[str]) -> str:
    """Validates user choice against an explicit list of allowed strings."""
    while True:
        choice = safe_input(f"Select an option ({'/'.join(allowed_choices)}): ").strip()
        if choice in allowed_choices:
            return choice
        display_error(f"Invalid selection. Expected one of: {', '.join(allowed_choices)}")


def get_valid_priority() -> str:
    """Prompts for rule priority weight. Defaults to 'reject' if left blank."""
    print("  Select priority weight:")
    print("    1. Must (Weight: 4)")
    print("    2. Important (Weight: 3)")
    print("    3. Nice (Weight: 2)")
    print("    4. Can consider (Weight: 1)")
    print("    5. No weight (Sets priority to 'reject')")

    choice_map = {
        "1": "must",
        "2": "important",
        "3": "nice",
        "4": "can consider"
    }

    while True:
        choice = safe_input("Enter priority (1-4, or press Enter / 5 for reject): ").strip()

        if choice in ["", "5"]:
            display_message("  [*] No weight provided. Setting priority to 'reject'.")
            return "reject"

        if choice in choice_map:
            return choice_map[choice]

        display_error("Invalid choice. Select 1-4, or press Enter / 5 for reject.")


# =====================================================================
# BUSINESS RULES MANAGEMENT & DUPLICATION GUARD
# =====================================================================


def display_current_rules(rules: list[dict]) -> None:
    """Prints all configured rules in an indexed list."""
    if not rules:
        display_message("\n  [i] No business rules currently configured.")
        return

    print("\n---------------- CURRENT BUSINESS RULES ----------------")
    for idx, rule in enumerate(rules, start=1):
        priority = rule.get("priority", "reject").upper()
        text = rule.get("text", "<unspecified>")
        print(f"  {idx}. [{priority}] {text}")
    print("-------------------------------------------------------")


def add_business_rules(rules: list[dict]) -> list[dict]:
    """Captures rules line-by-line with length checks and duplicate guards."""
    print("\n--- ADD BUSINESS RULES ---")
    print("Enter requirements one at a time.")

    while True:
        rule_num = len(rules) + 1
        print(f"\n[Rule #{rule_num}]")

        while True:
            text = safe_input("Enter rule requirement: ").strip()

            # Guard 1: Minimum content validation
            if len(text) < 5:
                display_error("Rule text too short. Enter at least 5 characters.")
                continue

            # Guard 2: Maximum sanity boundary check
            if len(text) > 300:
                display_error("Rule text too long (max 300 chars). Keep it concise.")
                continue

            # Guard 3: Case-insensitive duplication check
            is_duplicate = any(r.get("text", "").lower() == text.lower() for r in rules)
            if is_duplicate:
                display_error(f"Rule '{text}' is already in your list. Enter a unique rule.")
                continue

            break

        priority = get_valid_priority()
        rules.append({"text": text, "priority": priority})
        display_success(f"Added Rule #{rule_num} [{priority}]: '{text}'")

        print("\nDo you want to add another rule?")
        more = get_valid_menu_choice(["y", "n"])
        if more.lower() == "n":
            break

    return rules


def delete_single_rule(rules: list[dict]) -> list[dict]:
    """Safely removes an existing rule by index."""
    if not rules:
        display_message("\n  [i] No rules available to delete.")
        return rules

    display_current_rules(rules)
    print("\nEnter rule number to remove (or '0' to cancel):")

    valid_choices = [str(i) for i in range(len(rules) + 1)]
    choice = get_valid_menu_choice(valid_choices)

    if choice == "0":
        display_message("Deletion cancelled.")
        return rules

    try:
        removed_rule = rules.pop(int(choice) - 1)
        display_success(f"Removed Rule: '{removed_rule.get('text', '')}'")
    except IndexError:
        display_error("Selected rule index out of range.")

    return rules


def manage_business_rules(existing_rules: list[dict]) -> list[dict]:
    """Sub-menu interface for viewing, adding, and clearing rules."""
    rules = list(existing_rules)

    while True:
        print("\n=============================================")
        print("          BUSINESS RULES MANAGEMENT          ")
        print("=============================================")
        print(f"Total Rules Configured: {len(rules)}")
        print("1. View Current Rules")
        print("2. Add New Rule(s)")
        print("3. Delete a Specific Rule")
        print("4. Clear All Rules")
        print("5. Save & Return to Main Menu")
        print("=============================================")

        sub_choice = get_valid_menu_choice(["1", "2", "3", "4", "5"])

        if sub_choice == "1":
            display_current_rules(rules)
        elif sub_choice == "2":
            rules = add_business_rules(rules)
        elif sub_choice == "3":
            rules = delete_single_rule(rules)
        elif sub_choice == "4":
            if not rules:
                display_message("\n  [i] Rules list is already empty.")
                continue
            print("\nAre you sure you want to clear all rules?")
            if get_valid_menu_choice(["y", "n"]) == "y":
                rules.clear()
                display_success("All business rules cleared.")
        elif sub_choice == "5":
            return rules


# =====================================================================
# DIRECTORY & CANDIDATE LIMIT SELECTION
# =====================================================================


def scan_pdf_count(folder_path: str) -> tuple[bool, int, str]:
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
    except OSError as e:
        return False, 0, f"Operating system error reading '{folder_path}': {e}"

    pdf_files = [f for f in entries if f.lower().endswith(".pdf")]
    return True, len(pdf_files), ""


def get_valid_pdf_directory() -> str:
    """Validates host resume directories against path and permission errors."""
    print("\n--- STEP 1: RESUME FOLDER SELECTION ---")
    print("Tip: Press ENTER to use the default 'resumes' directory.\n")

    while True:
        folder_path = safe_input("Enter directory path [Default: resumes]: ").strip()

        if not folder_path:
            folder_path = "resumes"

        # Sanitize pasted shell paths
        folder_path = folder_path.strip("'\"").replace("\\ ", " ")

        is_valid, pdf_count, err_msg = scan_pdf_count(folder_path)

        if not is_valid:
            display_error(err_msg)
            continue

        if pdf_count == 0:
            display_error(f"No PDF files (.pdf) found in '{folder_path}'.")
            continue

        display_success(f"Found {pdf_count} PDF resume(s) in '{folder_path}'.")
        return folder_path


def get_valid_top_n_candidates(max_available: int = None) -> int:
    """Validates top N input against non-integers, zeros, and upper boundaries."""
    print("\n--- STEP 2: CANDIDATE OUTPUT LIMIT ---")
    while True:
        raw_val = safe_input("How many top candidates to return (e.g., 3, 5)? ").strip()

        if not raw_val.isdigit():
            display_error("Invalid input. Please enter a positive integer.")
            continue

        count = int(raw_val)
        if count <= 0:
            display_error("Limit must be at least 1.")
            continue

        if max_available and count > max_available:
            display_message(f"  [*] Notice: Only {max_available} PDF(s) available. Capping limit to {max_available}.")
            return max_available

        return count


def configure_resumes_and_limit() -> tuple[str, int]:
    """Coordinates directory and candidate limit selection."""
    folder = get_valid_pdf_directory()
    _, pdf_count, _ = scan_pdf_count(folder)
    limit = get_valid_top_n_candidates(max_available=pdf_count)
    display_success(f"Configured folder '{folder}' with candidate limit of {limit}.")
    return folder, limit


def get_valid_output_directory(current_output_dir: str = "output") -> str:
    """Validates and configures the directory where screening result JSON files are stored."""
    print("\n--- STEP: OUTPUT RESULTS FOLDER SELECTION ---")
    print(f"Tip: Press ENTER to use the current/default folder '{current_output_dir}'.\n")

    while True:
        folder_path = safe_input(f"Enter output directory path [Default: {current_output_dir}]: ").strip()

        if not folder_path:
            folder_path = current_output_dir

        # Sanitize pasted shell paths
        folder_path = folder_path.strip("'\"").replace("\\ ", " ")

        # Create folder if it doesn't already exist and test write permissions
        try:
            os.makedirs(folder_path, exist_ok=True)
            test_file = os.path.join(folder_path, ".write_test.tmp")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
        except PermissionError:
            display_error(f"Permission denied accessing or creating folder '{folder_path}'.")
            continue
        except OSError as e:
            display_error(f"Operating system error for folder '{folder_path}': {e}")
            continue

        display_success(f"Output folder configured: '{folder_path}'.")
        return folder_path


# =====================================================================
# RESULTS DISPLAY & FILE RECOVERY
# =====================================================================


def find_results_files_in_folder(output_dir: str = "output") -> list[str]:
    """Returns all result JSON files from the output folder, sorted newest first."""
    if not os.path.exists(output_dir) or not os.path.isdir(output_dir):
        return []

    pattern = os.path.join(output_dir, "*.json")
    all_files = glob.glob(pattern)

    result_files = []
    for filepath in all_files:
        basename = os.path.basename(filepath).lower()
        if basename != "resumes.json":
            result_files.append(filepath)

    try:
        result_files.sort(key=os.path.getmtime, reverse=True)
    except OSError:
        pass

    return result_files


def select_result_file_to_view(output_dir: str = "output") -> str | None:
    """Displays available screening result files and prompts user to pick one."""
    files = find_results_files_in_folder(output_dir)

    # Fallback to project root if folder is empty
    if not files:
        root_candidates = [
            f for f in glob.glob("filtered_resume_*.json") + glob.glob("ai_output.json")
            if os.path.isfile(f)
        ]
        if root_candidates:
            try:
                root_candidates.sort(key=os.path.getmtime, reverse=True)
            except OSError:
                pass
            files = root_candidates

    if not files:
        display_error(f"No results JSON files found in '{output_dir}'. Please run screening first.")
        return None

    if len(files) == 1:
        display_message(f"\n  [*] Found 1 result file: '{os.path.basename(files[0])}'")
        return files[0]

    print("\n---------------- AVAILABLE SCREENING RESULTS ----------------")
    print(f"  Target Folder: '{output_dir}'")
    for idx, filepath in enumerate(files, start=1):
        filename = os.path.basename(filepath)
        try:
            mtime = os.path.getmtime(filepath)
            # Format in Singapore Standard Time (SGT, UTC+8)
            time_str = datetime.fromtimestamp(mtime, tz=timezone.utc).astimezone(SGT_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
            size_kb = round(os.path.getsize(filepath) / 1024, 1)
            print(f"  {idx}. {filename}  [{time_str} SGT | {size_kb} KB]")
        except OSError:
            print(f"  {idx}. {filename}")
    print("-------------------------------------------------------------")

    print("\nEnter result number to view (or '0' to cancel):")
    valid_choices = [str(i) for i in range(len(files) + 1)]
    choice = get_valid_menu_choice(valid_choices)

    if choice == "0":
        display_message("View results cancelled.")
        return None

    return files[int(choice) - 1]


def display_screening_results(ranked_candidates: list[dict], top_n: int = None) -> None:
    """Renders candidate records cleanly, guarding against missing keys or invalid types."""
    if not isinstance(ranked_candidates, list) or not ranked_candidates:
        display_message("\n  [i] No candidate results available to display.")
        return

    display_list = ranked_candidates[0].get("accepted", ranked_candidates) if isinstance(ranked_candidates[0], dict) else ranked_candidates
    if top_n is not None and isinstance(top_n, int):
        display_list = display_list[:top_n]

    # Enforce top_n candidate limit if configured
    if top_n is not None and top_n > 0:
        display_list = display_list[:top_n]

    print("\n" + "=" * 75)
    print("                       TOP RANKED CANDIDATES")
    print("=" * 75)

    for idx, candidate in enumerate(display_list, start=1):
        if not isinstance(candidate, dict):
            continue

        rank = candidate.get("rank", idx)

        # Name fallback: name -> filename -> placeholder
        name = candidate.get("name") or candidate.get("file") or "Unknown Candidate"
        if not str(name).strip():
            name = candidate.get("file", "Unknown Candidate")

        # Defensive score formatting
        raw_score = candidate.get("score")
        if raw_score is not None:
            try:
                score_str = f"{float(raw_score):.1f}%"
            except (ValueError, TypeError):
                score_str = str(raw_score)
        else:
            outcome = candidate.get("outcome", "disqualified")
            score_str = f"N/A ({outcome})"

        reason = candidate.get("reason", "No evaluation summary provided.")

        print(f"\n  [Rank #{rank}]  {str(name).strip()}")
        print(f"      Score  : {score_str}")
        print(f"      Reason : {reason}")

    print("\n" + "-" * 75)
    print("  [*] Note: Complete details saved to JSON output file")
    print("=" * 75 + "\n")


def view_saved_results(file_path: str = None, top_n: int = None, output_dir: str = "output") -> None:
    """Reads and parses saved JSON output with protection against corruption."""
    if file_path:
        target = file_path
    else:
        target = select_result_file_to_view(output_dir)

    if not target:
        return

    # Check for empty file
    try:
        if os.path.getsize(target) == 0:
            display_error(f"'{target}' is empty. Re-run screening to generate output.")
            return
    except OSError as e:
        display_error(f"Failed to check file size for '{target}': {e}")
        return

    display_message(f"\n  [i] Reading results from '{target}'...")

    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            display_error(f"'{target}' contains invalid data structure (expected JSON array).")
            return

        display_screening_results(data, top_n=top_n)

    except json.JSONDecodeError as err:
        display_error(f"Corrupted JSON in '{target}': {err.msg} (line {err.lineno})")
    except PermissionError:
        display_error(f"Permission denied reading '{target}'.")
    except Exception as e:
        display_error(f"Unexpected error while opening '{target}': {e}")


# =====================================================================
# AGGREGATOR FUNCTION FOR EXTERNAL MANAGERS (MENU DRIVEN)
# =====================================================================


def get_employer_inputs(rerun:dict = None) -> dict:
    """Interactive menu dashboard enforcing prerequisite guards before pipeline handoff."""
    config = rerun if rerun else {
        "business_rules": [],
        "pdf_directory": "resumes",
        "top_n": 3,
        "output_directory": "output"
    }
    if "output_directory" not in config:
        config["output_directory"] = "output"

    while True:
        rules_status = (
            f"{len(config['business_rules'])} Rule(s) Configured"
            if config["business_rules"]
            else "NOT SET (Required)"
        )

        print("\n=============================================")
        print("          RESUME SCREENER SETUP MENU         ")
        print("=============================================")
        print(f"1. Manage Business Rules Criteria  [{rules_status}]")
        print(f"2. Configure Resumes & Limit       [Folder: '{config['pdf_directory']}', Limit: {config['top_n']}]")
        print(f"3. Configure Output Results Folder [Folder: '{config['output_directory']}']")
        print("4. Proceed to Resume Screening")
        print("5. View Screening Results (from JSON)")
        print("6. Exit Application")
        print("=============================================")

        choice = get_valid_menu_choice(["1", "2", "3", "4", "5", "6"])

        if choice == "1":
            config["business_rules"] = manage_business_rules(config["business_rules"])

        elif choice == "2":
            folder, limit = configure_resumes_and_limit()
            config["pdf_directory"] = folder
            config["top_n"] = limit

        elif choice == "3":
            config["output_directory"] = get_valid_output_directory(config["output_directory"])

        elif choice == "4":
            if not config["business_rules"]:
                display_error("You must configure at least one Business Rule (Option 1) before starting!")
                continue

            is_valid, pdf_count, err_msg = scan_pdf_count(config["pdf_directory"])
            if not is_valid:
                display_error(f"{err_msg} Update folder via Option 2.")
                continue

            if pdf_count == 0:
                display_error(f"No PDFs found in '{config['pdf_directory']}'. Update via Option 2.")
                continue

            if config["top_n"] > pdf_count:
                display_message(f"  [*] Notice: Capping candidate limit from {config['top_n']} to available ({pdf_count}).")
                config["top_n"] = pdf_count

            display_success("Configuration verified! Handing off to main pipeline...\n")
            return config

        elif choice == "5":
            view_saved_results(file_path=None, top_n=config["top_n"], output_dir=config["output_directory"])

        elif choice == "6":
            display_message("\nExiting Resume Screener. Goodbye!")
            sys.exit(0)

# =====================================================================
# LOCAL STANDALONE TEST
# =====================================================================

if __name__ == "__main__":
    display_message("=== TESTING I/O MANAGER INTERACTIVE MENU ===")
    inputs = get_employer_inputs()
    display_message("\n--- RETURNED DICTIONARY FOR OTHER MANAGERS ---")
    display_message(str(inputs))