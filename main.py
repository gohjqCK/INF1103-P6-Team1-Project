import json
from pathlib import Path

import AI_Manager
import Data_Manager
import Logic_Manager
from io_manager_modules.io_manager_cli import CLIIOManager

AI_OUTPUT_FILE = "ai_output.json"


def main():
    # Instantiate the Object-Oriented I/O Manager
    io_manager = CLIIOManager()

    if AI_Manager.check_connection() == False:
        io_manager.display_error(
            "Cannot connect to Ollama or required models are missing.\n"
            "Please install required dependancies or check if Ollama is running."
        )
        pass

    config = io_manager.get_employer_inputs()
    rules = config["business_rules"]
    pdf_directory = config["pdf_directory"]
    top_n = config["top_n"]
    outDir = config["output_directory"]
    rerun = False

    while True:
        if rerun == True:
            input("\nScreening complete, press any key to return to menu")
            config = io_manager.get_employer_inputs(config)
            rules = config["business_rules"]
            pdf_directory = config["pdf_directory"]
            top_n = config["top_n"]
            outDir = config["output_directory"]

        io_manager.display_message("\n[1/4] Generating AI prompt from business rules")
        rules = AI_Manager.add_keywords(rules)

        io_manager.display_message("\n[2/4] Parsing resumes")
        resumes = Data_Manager.parse_resumes(folder=pdf_directory, output_file="resumes.json")
        
        if not resumes:
            io_manager.display_error("No resumes were found or successfully parsed in the specified directory.")
            return

        io_manager.display_message("\n[3/4] Screening resumes")
        if AI_Manager.check_connection() == True:
            AI_Manager.screen_resumes(rules, resumes, resumes_file="resumes.json", results_file=AI_OUTPUT_FILE)
            io_manager.display_message("\n[4/4] Validating and ranking results")
            results_path = Path(AI_OUTPUT_FILE)

            if (
                Logic_Manager.validate_file_exists_func(results_path) == 0
                and Logic_Manager.validate_file_type_func(results_path) == 0
                and Logic_Manager.validate_file_empty_func(results_path) == 0
            ):
                with open(results_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                if Logic_Manager.validate_resume_func(data) == 0 and Logic_Manager.validate_resume_keys_func(data) == "":      
                    accepted_resume, rejected_resume, invalid_resume = Logic_Manager.filter_resume_func(data)
                    Data_Manager.outputfile_func(accepted_resume, rejected_resume, invalid_resume, outDir)
                    sorted_resume = Logic_Manager.sort_resume_func(accepted_resume)

                    io_manager.display_success("Resumes successfully screened")
                    io_manager.display_screening_results(sorted_resume, top_n=top_n)
                    rerun = True

                else:
                    io_manager.display_error("Logic Manager detected invalid data types or missing keys in the JSON file")
                    break

            else:
                io_manager.display_error("Logic Manager could not validate the JSON file")
                break

        else:
            io_manager.display_error("Cannot connect to Ollama or required models are missing.")
            io_manager.display_message("\n[4/4] Running offline rudimentry screening (Less accurate)")
            offline_resumes = Logic_Manager.offline_screening_func(resumes, rules)
            accepted_resume, rejected_resume, invalid_resume = Logic_Manager.filter_resume_func(offline_resumes)
            Data_Manager.outputfile_func(accepted_resume, rejected_resume, invalid_resume, outDir)
            sorted_resume = Logic_Manager.sort_resume_func(offline_resumes)

            io_manager.display_success("Offline screening complete")
            io_manager.display_screening_results(sorted_resume, top_n=top_n)
            rerun = True


if __name__ == "__main__":
    main()