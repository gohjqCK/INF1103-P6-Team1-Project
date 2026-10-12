import json
from pathlib import Path

import AI_Manager
import Data_Manager
import IO_manager
import Logic_Manager


def main():
    if not AI_Manager.check_connection():
        IO_manager.display_error("Cannot connect to Ollama or required models are missing.\nPlease install required dependancies.")
        return

    config = IO_manager.get_employer_inputs()
    rules = config["business_rules"]
    pdf_directory = config["pdf_directory"]
    top_n = config["top_n"]

    IO_manager.display_message("\n[1/4] Generating AI prompt from business rules")
    rules = AI_Manager.add_keywords(rules)

    IO_manager.display_message("\n[2/4] Parsing resumes")
    resumes = Data_Manager.parse_resumes(folder=pdf_directory, output_file="resumes.json")
    
    if not resumes:
        IO_manager.display_error("No resumes were found or successfully parsed in the specified directory.")
        return

    IO_manager.display_message("\n[3/4] Screening resumes")
    AI_Manager.screen_resumes(rules, resumes, resumes_file="resumes.json", results_file="results.json")

    IO_manager.display_message("\n[4/4] Validating and ranking results")
    results_path = Path("results.json")

    if Logic_Manager.validate_file_exists_func(results_path) == 0 and Logic_Manager.validate_file_type_func(results_path) == 0 and Logic_Manager.validate_file_empty_func(results_path) == 0:
        with open(results_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if Logic_Manager.validate_resume_func(data) == 0 and Logic_Manager.validate_resume_keys_func(data) == 0:      
            accepted_resume, rejected_resume, invalid_resume = Logic_Manager.filter_resume_func(data)
            Data_Manager.outputfile_func(accepted_resume, rejected_resume, invalid_resume)
            sorted_resume = Logic_Manager.sort_resume_func(accepted_resume)

            IO_manager.display_success("Resumes successfully screened")
            IO_manager.display_screening_results(sorted_resume, top_n=top_n)

        else:
            IO_manager.display_error("Logic Manager detected invalid data types or missing keys in results.json.")

    else:
        IO_manager.display_error("Logic Manager could not validate the results.json file.")

if __name__ == "__main__":
    main()
