from pathlib import Path
import json
from json.decoder import JSONDecodeError
#ai_output_file is the file path
class ResultsPath:
    def __init__(self,ai_output_file):
        self.__results_path=ai_output_file

    @property
    def validate_file_exists_func(self):
        if self.__results_path.is_file():
            return 0
        else:
            return"LM: The file does not exist. Either AI Output wrong file name or did not output at all"
    @property
    #Checks if file is json type
    def validate_file_type_func(self):
        if self.__results_path.suffix.lower()==".json":
            return 0
        else:
            return "LM: AI output wrong file type"
    @property
    #Checks if json file is empty
    def validate_file_empty_func(self):
        try:
            with open(self.__results_path, 'r') as file:
                data = json.load(file)
            if not data: 
                return "LM: The file contains an empty JSON object or array ({ or [])."
            else:
                return 0
        except JSONDecodeError:
            # This catches completely blank files or files with malformed JSON
            return "LM: The file is completely empty or contains invalid JSON."