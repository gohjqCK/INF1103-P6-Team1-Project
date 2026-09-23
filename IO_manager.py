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


def get_valid_business_rules_prompt() -> str:
    """Asks the employer for evaluation criteria.

    Reads multi-line text until double-ENTER is pressed, then makes sure
    it's long enough (>= 15 chars) so the AI gets actual useful context.
    """
    print("\n--- EMPLOYER BUSINESS RULES & EVALUATION CRITERIA ---")
    print("Define criteria for the AI (e.g., mandatory skills, minimum experience, key duties):")
    print("(Press ENTER twice on a blank line when finished typing)\n")

    while True:
        lines = []
        while True:
            line = input()
            # Double blank line indicates the user is done typing
            if line == "" and lines and lines[-1] == "":
                lines.pop()
                break
            lines.append(line)

        raw_prompt = "\n".join(lines).strip()

        if len(raw_prompt) >= 15:
            display_success("Business rules prompt accepted.")
            return raw_prompt

        display_error("Input too short or empty. Provide detailed criteria (minimum 15 chars).")


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
        "business_rules": None,
        "pdf_directory": "resumes",  # default
        "top_n": 3,  # default
    }

    while True:
        # Status indicators for menu display
        rules_status = (
            "Set" if config["business_rules"] else "NOT SET (Required)"
        )

        print("\n=============================================")
        print("          RESUME SCREENER SETUP MENU         ")
        print("=============================================")
        print(f"1. Input Business Rules Criteria [{rules_status}]")
        print(
            "2. Select Resume Directory      "
            f" [Current: '{config['pdf_directory']}']"
        )
        print(
            "3. Set Candidate Output Limit   "
            f" [Current: {config['top_n']}]"
        )
        print("4. Proceed to Resume Screening")
        print("=============================================")

        choice = get_valid_menu_choice(["1", "2", "3", "4"])

        if choice == "1":
            config["business_rules"] = get_valid_business_rules_prompt()

        elif choice == "2":
            config["pdf_directory"] = get_valid_pdf_directory()

        elif choice == "3":
            # Check how many PDFs are available in selected folder to pass as limit cap
            if os.path.exists(config["pdf_directory"]) and os.path.isdir(
                config["pdf_directory"]
            ):
                pdf_files = [
                    f
                    for f in os.listdir(config["pdf_directory"])
                    if f.lower().endswith(".pdf")
                ]
                max_count = len(pdf_files)
            else:
                max_count = None

            config["top_n"] = get_valid_top_n_candidates(
                max_available=max_count
            )

        elif choice == "4":
            # Guard check 1: Must enter business rules before starting
            if not config["business_rules"]:
                display_error(
                    "You must input Business Rules Criteria (Option 1) before"
                    " starting!"
                )
                continue

            # Guard check 2: Directory must exist and contain PDFs
            if not os.path.exists(config["pdf_directory"]):
                display_error(
                    f"Selected directory '{config['pdf_directory']}' does not"
                    " exist. Please update Option 2."
                )
                continue

            pdf_files = [
                f
                for f in os.listdir(config["pdf_directory"])
                if f.lower().endswith(".pdf")
            ]
            if not pdf_files:
                display_error(
                    f"No PDF resumes found in '{config['pdf_directory']}'."
                    " Add PDFs or pick another folder (Option 2)."
                )
                continue

            # Auto-cap top_n if candidate limit exceeds available PDFs
            if config["top_n"] > len(pdf_files):
                display_message(
                    f"  [*] Notice: Capping candidate limit from {config['top_n']} to total available ({len(pdf_files)})."
                )
                config["top_n"] = len(pdf_files)

            display_success(
                "Configuration complete! Handing off to main pipeline...\n"
            )
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