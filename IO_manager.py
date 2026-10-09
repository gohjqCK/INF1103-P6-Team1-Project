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


def get_valid_business_rules() -> list[dict]:
    """Interactively collects business rules line by line with priority weights.

    Returns a list of dictionaries formatted for downstream evaluation.
    """
    print("\n--- EMPLOYER BUSINESS RULES & EVALUATION CRITERIA ---")
    print("Add your evaluation rules one by one.")

    rules = []

    while True:
        rule_num = len(rules) + 1
        print(f"\n[Rule #{rule_num}]")

        # 1. Capture rule text
        while True:
            text = input("Enter rule requirement: ").strip()
            if len(text) >= 5:
                break
            display_error("Rule text is too short. Please provide a clear requirement (min 5 chars).")

        # 2. Capture priority level (defaults to 'reject' if no weight is given)
        priority = get_valid_priority()

        # 3. Save rule
        rules.append({"text": text, "priority": priority})
        display_success(f"Added Rule #{rule_num} [{priority}]: '{text}'")

        # 4. Prompt if user has more rules
        print("\nDo you want to add another rule?")
        more = get_valid_menu_choice(["y", "n"])
        if more.lower() == "n":
            break

    display_success(f"Configured total of {len(rules)} business rule(s).")
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

# =====================================================================
# AGGREGATOR FUNCTION FOR EXTERNAL MANAGERS
# =====================================================================


def get_employer_inputs() -> dict:
    """Displays an interactive configuration menu before launching the pipeline."""
    config = {
        "business_rules": [],       # Stores list of rule dicts: [{"text": ..., "priority": ...}]
        "pdf_directory": "resumes",  # Default directory
        "top_n": 3                   # Default limit
    }

    while True:
        # Show how many rules are configured
        if config["business_rules"]:
            rules_status = f"{len(config['business_rules'])} Rule(s) Configured"
        else:
            rules_status = "NOT SET (Required)"

        print("\n=============================================")
        print("          RESUME SCREENER SETUP MENU         ")
        print("=============================================")
        print(f"1. Input Business Rules Criteria [{rules_status}]")
        print(f"2. Select Resume Directory       [Current: '{config['pdf_directory']}']")
        print(f"3. Set Candidate Output Limit    [Current: {config['top_n']}]")
        print("4. Proceed to Resume Screening")
        print("=============================================")

        choice = get_valid_menu_choice(["1", "2", "3", "4"])

        if choice == "1":
            config["business_rules"] = get_valid_business_rules()

        elif choice == "2":
            config["pdf_directory"] = get_valid_pdf_directory()

        elif choice == "3":
            if os.path.exists(config["pdf_directory"]) and os.path.isdir(config["pdf_directory"]):
                pdf_files = [f for f in os.listdir(config["pdf_directory"]) if f.lower().endswith(".pdf")]
                max_count = len(pdf_files)
            else:
                max_count = None

            config["top_n"] = get_valid_top_n_candidates(max_available=max_count)

        elif choice == "4":
            if not config["business_rules"]:
                display_error("You must input Business Rules Criteria (Option 1) before starting!")
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

# =====================================================================
# LOCAL STANDALONE TEST
# =====================================================================

if __name__ == "__main__":
    # Quick sanity check when running io_manager.py directly
    display_message("=== TESTING I/O MANAGER IMPORTABLE FUNCTIONS ===")
    inputs = get_employer_inputs()
    display_message("\n--- RETURNED DICTIONARY FOR OTHER MANAGERS ---")
    display_message(str(inputs))