import json
import os

# These functions wrap print statements to centralize formatting 
# and keep console output styling consistent across the whole application.


def display_message(message: str) -> None:
    """Prints standard application output messages."""
    print(message)


def display_error(error_message: str) -> None:
    """Prints error messages with consistent alert formatting."""
    print(f"\n  [!] ERROR: {error_message}\n")


def display_success(success_message: str) -> None:
    """Prints success confirmation messages with positive feedback styling."""
    print(f"  [+] SUCCESS: {success_message}")


# =====================================================================
# INPUT VALIDATION FUNCTIONS
# =====================================================================


def get_valid_menu_choice(allowed_choices: list[str]) -> str:
    """Keeps re-prompting until the user picks a choice from our allowed list."""
    while True:
        choice = input(f"Select an option ({'/'.join(allowed_choices)}): ").strip()
        if choice in allowed_choices:
            return choice
        display_error(f"Invalid choice. Allowed options: {', '.join(allowed_choices)}")


def get_valid_priority() -> str:
    """Prompts for a priority weight.

    If the user presses Enter without picking a weight (or selects option 5),
    the rule has no weight assigned and defaults to 'reject'.
    """
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
        choice = input("Enter priority (1-4, or press Enter for no weight/reject): ").strip()

        # If user leaves it blank or types 5, treat as no weight provided
        if choice in ["", "5"]:
            display_message("  [*] No weight provided. Setting priority to 'reject'.")
            return "reject"

        if choice in choice_map:
            return choice_map[choice]

        display_error("Invalid choice. Select 1-4, or press Enter / 5 for no weight/reject.")


def display_current_rules(rules: list[dict]) -> None:
    """Prints all configured rules in a numbered list."""
    if not rules:
        display_message("\n  [i] No business rules currently configured.")
        return

    print("\n---------------- CURRENT BUSINESS RULES ----------------")
    for idx, rule in enumerate(rules, start=1):
        print(f"  {idx}. [{rule['priority'].upper()}] {rule['text']}")
    print("-------------------------------------------------------")


def add_business_rules(rules: list[dict]) -> list[dict]:
    """Interactively prompts user to add rules with priority weights and duplication checks."""
    print("\n--- ADD BUSINESS RULES ---")
    print("Enter requirements one at a time.")

    while True:
        rule_num = len(rules) + 1
        print(f"\n[Rule #{rule_num}]")

        # 1. Capture and validate rule text
        while True:
            text = input("Enter rule requirement: ").strip()
            if len(text) < 5:
                display_error("Rule text is too short. Please provide a clear requirement (min 5 chars).")
                continue

            # Duplication Guard: Check if identical requirement already exists (case-insensitive)
            is_duplicate = any(r["text"].lower() == text.lower() for r in rules)
            if is_duplicate:
                display_error(f"Rule '{text}' already exists in your criteria list. Please enter a different rule.")
                continue

            break

        # 2. Capture priority level
        priority = get_valid_priority()

        # 3. Append valid rule
        rules.append({"text": text, "priority": priority})
        display_success(f"Added Rule #{rule_num} [{priority}]: '{text}'")

        # 4. Prompt if user wants to add another rule right away
        print("\nDo you want to add another rule?")
        more = get_valid_menu_choice(["y", "n"])
        if more.lower() == "n":
            break

    return rules


def delete_single_rule(rules: list[dict]) -> list[dict]:
    """Allows user to select and delete a specific rule by number."""
    if not rules:
        display_message("\n  [i] No rules available to delete.")
        return rules

    display_current_rules(rules)
    print("\nEnter the rule number you want to remove (or '0' to cancel):")

    valid_choices = [str(i) for i in range(len(rules) + 1)]
    choice = get_valid_menu_choice(valid_choices)

    if choice == "0":
        display_message("Deletion cancelled.")
        return rules

    removed_rule = rules.pop(int(choice) - 1)
    display_success(f"Removed Rule: '{removed_rule['text']}'")
    return rules


def manage_business_rules(existing_rules: list[dict]) -> list[dict]:
    """Sub-menu dashboard to view, add, delete, or clear business rules."""
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
            confirm = get_valid_menu_choice(["y", "n"])
            if confirm == "y":
                rules.clear()
                display_success("All business rules cleared.")

        elif sub_choice == "5":
            return rules


def get_valid_pdf_directory() -> str:
    """Gets folder path for PDF resumes.

    Defaults to 'resumes' if empty (helps with Docker), cleans up drag-and-drop
    paths, and checks if the folder actually has .pdf files.
    """
    print("\n--- RESUME FOLDER SELECTION ---")
    print("Tip: Place your PDF resumes inside the 'resumes' folder,")
    print("     or press ENTER to use the default 'resumes' directory.\n")

    while True:
        folder_path = input("Enter directory path [Default: resumes]: ").strip()

        # Fallback to default directory if user just hits enter
        if not folder_path:
            folder_path = "resumes"

        # Fix formatting issues if user drags & drops a folder directly into the terminal
        folder_path = folder_path.strip("'\"").replace("\\ ", " ")

        if not os.path.exists(folder_path):
            display_error(f"Path '{folder_path}' does not exist.")
        elif not os.path.isdir(folder_path):
            display_error(f"Path '{folder_path}' is a file, not a directory.")
        else:
            pdf_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".pdf")]
            if not pdf_files:
                display_error(f"No PDF files (.pdf) found in '{folder_path}'.")
            else:
                display_success(f"Found {len(pdf_files)} PDF resume(s) in '{folder_path}'.")
                return folder_path


def get_valid_top_n_candidates(max_available: int = None) -> int:
    """Gets the top N candidates count from the user.

    Ensures it's a valid integer > 0 and caps it if the requested count
    exceeds total available PDFs found.
    """
    while True:
        user_input = input("\nHow many top candidates should be returned (e.g., 3, 5, 10)? ").strip()

        if not user_input.isdigit():
            display_error("Invalid input. Enter a positive whole number.")
            continue

        count = int(user_input)
        if count <= 0:
            display_error("Number must be at least 1.")
            continue

        # Automatically cap count so we don't request more candidates than we have PDFs
        if max_available and count > max_available:
            display_message(f"  [*] Notice: Only {max_available} PDF(s) available. Capping limit to {max_available}.")
            return max_available

        return count


def configure_resumes_and_limit() -> tuple[str, int]:
    """Sequentially prompts for resume directory, then immediately prompts

    for the candidate limit based on the number of PDFs found.
    """
    folder = get_valid_pdf_directory()

    # Determine available PDFs in chosen directory to enforce realistic upper bound
    pdf_files = [f for f in os.listdir(folder) if f.lower().endswith(".pdf")]
    limit = get_valid_top_n_candidates(max_available=len(pdf_files))

    display_success(f"Configured directory '{folder}' with candidate limit of {limit}.")
    return folder, limit


# =====================================================================
# RESULTS DISPLAY (LOGIC MANAGER OUTPUT)
# =====================================================================

def display_screening_results(ranked_candidates: list[dict], top_n: int = None) -> None:
    """Takes ranked candidate records and displays a clean CLI leaderboard.
    Optionally slices output to top_n candidates.
    """
    if not ranked_candidates:
        display_message("\n  [i] No ranked candidates to display.")
        return

    # Slice list if top_n is specified
    display_list = ranked_candidates[:top_n] if top_n else ranked_candidates

    print("\n" + "=" * 75)
    print("                       TOP RANKED CANDIDATES")
    print("=" * 75)

    for idx, candidate in enumerate(display_list, start=1):
        rank = candidate.get("rank", idx)
        name = candidate.get("name", "").strip() or candidate.get("file", "Unknown Candidate")
        
        score = candidate.get("score")
        if score is not None:
            score_str = f"{score:.1f}%"
        else:
            outcome = candidate.get("outcome", "disqualified")
            score_str = f"N/A ({outcome})"

        reason = candidate.get("reason", "No evaluation summary provided.")

        print(f"\n  [Rank #{rank}]  {name}")
        print(f"      Score  : {score_str}")
        print(f"      Reason : {reason}")

    print("\n" + "-" * 75)
    print("  [*] Full details (contact, skills, experience) saved to results.json")
    print("=" * 75 + "\n")


def view_saved_results(file_path: str = "results.json", top_n: int = None) -> None:
    """Loads results.json from disk and passes it to display_screening_results."""
    if not os.path.exists(file_path):
        display_error(f"'{file_path}' not found. Please run the screening first (Option 3).")
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            display_error(f"'{file_path}' does not contain a valid list.")
            return

        display_screening_results(data, top_n=top_n)

    except json.JSONDecodeError:
        display_error(f"Could not parse '{file_path}'. File appears damaged or incomplete.")
    except Exception as e:
        display_error(f"Failed to read results: {e}")


# =====================================================================
# AGGREGATOR FUNCTION FOR EXTERNAL MANAGERS
# =====================================================================


def get_employer_inputs() -> dict:
    """Displays the main interactive configuration menu."""
    config = {
        "business_rules": [],       # Stores list of rule dicts: [{"text": ..., "priority": ...}]
        "pdf_directory": "resumes",  # Default directory
        "top_n": 3                   # Default limit
    }

    while True:
        if config["business_rules"]:
            rules_status = f"{len(config['business_rules'])} Rule(s) Configured"
        else:
            rules_status = "NOT SET (Required)"

        print("\n=============================================")
        print("          RESUME SCREENER SETUP MENU         ")
        print("=============================================")
        print(f"1. Manage Business Rules Criteria [{rules_status}]")
        print(f"2. Configure Resumes & Limit      [Folder: '{config['pdf_directory']}', Limit: {config['top_n']}]")
        print("3. Proceed to Resume Screening")
        print("4. View Screening Results (from results.json)")
        print("=============================================")

        choice = get_valid_menu_choice(["1", "2", "3", "4"])

        if choice == "1":
            config["business_rules"] = manage_business_rules(config["business_rules"])

        elif choice == "2":
            folder, limit = configure_resumes_and_limit()
            config["pdf_directory"] = folder
            config["top_n"] = limit

        elif choice == "3":
            if not config["business_rules"]:
                display_error("You must configure at least one Business Rule (Option 1) before starting!")
                continue

            if not os.path.exists(config["pdf_directory"]):
                display_error(f"Selected directory '{config['pdf_directory']}' does not exist. Please update Option 2.")
                continue

            pdf_files = [f for f in os.listdir(config["pdf_directory"]) if f.lower().endswith(".pdf")]
            if not pdf_files:
                display_error(f"No PDF resumes found in '{config['pdf_directory']}'. Add PDFs or pick another folder (Option 2).")
                continue

            if config["top_n"] > len(pdf_files):
                display_message(f"  [*] Notice: Capping candidate limit from {config['top_n']} to total available ({len(pdf_files)}).")
                config["top_n"] = len(pdf_files)

            display_success("Configuration complete! Handing off to main pipeline...\n")
            return config

        elif choice == "4":
            # Display results from results.json using current top_n limit
            view_saved_results(file_path="results.json", top_n=config["top_n"])


# =====================================================================
# LOCAL STANDALONE TEST
# =====================================================================

if __name__ == "__main__":
    # Quick sanity check when running io_manager.py directly
    display_message("=== TESTING I/O MANAGER IMPORTABLE FUNCTIONS ===")
    inputs = get_employer_inputs()
    display_message("\n--- RETURNED DICTIONARY FOR OTHER MANAGERS ---")
    display_message(str(inputs))