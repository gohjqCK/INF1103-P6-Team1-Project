import json
from pathlib import Path

import AI_Manager
import Data_Manager
import IO_manager
import Logic_Manager


def main():
    # 1. Welcome banner
    IO_manager.display_message("=" * 50)
    IO_manager.display_message("          AI RESUME CHECKER          ")
    IO_manager.display_message("=" * 50)

    # 2. Check Ollama server connection and required models via AI Manager
    if not AI_Manager.check_connection():
        IO_manager.display_error(
            "Cannot connect to Ollama or required models are missing. "
            "Please ensure Ollama is running and models are downloaded."
        )
        return

    # 3. Get employer configuration and business rules via IO Manager setup menu
    config = IO_manager.get_employer_inputs()
    rules = config["business_rules"]
    pdf_directory = config["pdf_directory"]
    top_n = config["top_n"]

    # 4. Generate AI keywords for the business rules via AI Manager[cite: 3]
    IO_manager.display_message("\n[Step 1/4] Generating AI keywords for business rules...")
    rules = AI_Manager.add_keywords(rules)

    # 5. Parse and structure PDF resumes from the selected directory via Data Manager[cite: 4]
    IO_manager.display_message(f"\n[Step 2/4] Parsing resumes from directory '{pdf_directory}'...")
    resumes = Data_Manager.parse_resumes(folder=pdf_directory, output_file="resumes.json")
    
    if not resumes:
        IO_manager.display_error("No resumes were found or successfully parsed in the specified directory.")
        return

    # 6. Screen resumes against rules using the local AI model via AI Manager[cite: 3]
    IO_manager.display_message("\n[Step 3/4] Screening resumes with AI Manager...")
    AI_Manager.screen_resumes(rules, resumes, resumes_file="resumes.json", results_file="results.json")

    # 7. Validate, filter, export, and sort screening results via Logic Manager[cite: 2]
    IO_manager.display_message("\n[Step 4/4] Validating, filtering, and ranking results with Logic Manager...")
    results_path = Path("results.json")

    # Perform comprehensive validations provided by Logic Manager[cite: 2]
    if (
        Logic_Manager.validate_file_exists_func(results_path) == 0
        and Logic_Manager.validate_file_type_func(results_path) == 0
        and Logic_Manager.validate_file_empty_func(results_path) == 0
    ):
        with open(results_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if (
            Logic_Manager.validate_resume_func(data) == 0
            and Logic_Manager.validate_resume_keys_func(data) == 0
        ):
            # Filter into valid (scored), rejected, and invalid lists[cite: 2]
            filtered_resume, rejected_resume, invalid_resume = Logic_Manager.filter_resume_func(data)

            # Output separated audit files[cite: 2]
            timestamp = Logic_Manager.date_time_format_func()
            Logic_Manager.outputfile_func(rejected_resume, f"rejected_resume_{timestamp}.json")
            Logic_Manager.outputfile_func(invalid_resume, f"invalid_resume_{timestamp}.json")

            # Sort top candidates using merge sort and save to filtered_resume_<timestamp>.json[cite: 2]
            sorted_resume = Logic_Manager.sort_resume_func(filtered_resume)

            IO_manager.display_success("Pipeline execution completed successfully!")

            # 8. Display formatted leaderboard via IO Manager[cite: 1]
            IO_manager.display_screening_results(sorted_resume, top_n=top_n)
        else:
            IO_manager.display_error("Logic Manager detected invalid data types or missing keys in results.json.")
    else:
        IO_manager.display_error("Logic Manager could not validate the results.json file.")


if __name__ == "__main__":
    main()