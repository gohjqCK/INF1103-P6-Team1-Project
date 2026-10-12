import json
from pathlib import Path

import AI_Manager
import Data_Manager
import IO_manager
import Logic_Manager


def main():
    if AI_Manager.check_connection() == False:
        IO_manager.display_error("Cannot connect to Ollama or required models are missing.\nPlease install required dependancies or check if Ollama is running.")
        pass

    config = IO_manager.get_employer_inputs()
    rules = config["business_rules"]
    pdf_directory = config["pdf_directory"]
    top_n = config["top_n"]
    rerun = False

    while True:
        if rerun == True:
            input("\nScreening complete, press any key to return to menu")
            IO_manager.get_employer_inputs(config)

        IO_manager.display_message("\n[1/4] Generating AI prompt from business rules")
        rules = AI_Manager.add_keywords(rules)

        IO_manager.display_message("\n[2/4] Parsing resumes")
        resumes = Data_Manager.parse_resumes(folder=pdf_directory, output_file="resumes.json")
        
        if not resumes:
            IO_manager.display_error("No resumes were found or successfully parsed in the specified directory.")
            return

        IO_manager.display_message("\n[3/4] Screening resumes")
        if AI_Manager.check_connection() == True:
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
                    rerun = True

                else:
                    IO_manager.display_error("Logic Manager detected invalid data types or missing keys in the JSON file")

            else:
                IO_manager.display_error("Logic Manager could not validate the JSON file")

        else:
            IO_manager.display_error("Cannot connect to Ollama or required models are missing.")
            IO_manager.display_message("\n[4/4] Running offline rudimentry screening (Less accurate)")
            offline_resumes = Logic_Manager.offline_screening_func(resumes, rules)
            accepted_resume, rejected_resume, invalid_resume = Logic_Manager.filter_resume_func(offline_resumes)
            Data_Manager.outputfile_func(accepted_resume, rejected_resume, invalid_resume)
            sorted_resume = Logic_Manager.sort_resume_func(offline_resumes)

            IO_manager.display_success("Offline screening complete")
            IO_manager.display_screening_results(sorted_resume, top_n=top_n)
            return
        

if __name__ == "__main__":
    main()
