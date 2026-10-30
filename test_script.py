import Logic_Manager
import json
from pathlib import Path
Path("Test_Script").mkdir(exist_ok=True)

with open("Test_Script/Error_Data_Format.json", "w", encoding="utf-8") as f:
    json.dump({"Format": "Incorrect"}, f, indent=4)

with open("Test_Script/Error_Missing_Keys.json", "w", encoding="utf-8") as f:
    json.dump([{"Value 1": "Hakim", "score": 10.0, "Missing": "Outcome"},{"Value 2": "Chi Yang", "outcome": "scored", "missing": "score"}], f, indent=4)

with open("Test_Script/Error_Empty.json", "w", encoding="utf-8") as f:
    f.write("")

Path("Test_Script/Error_fileType.pdf").touch()

testfile1=Path("EmptyFile")
output=Logic_Manager.validate_file_exists_func(testfile1)
print(output+"\n")

testfile2=Path("Test_Script/Error_fileType.pdf")
output=Logic_Manager.validate_file_type_func(testfile2)
print(output+"\n")

testfile3=Path("Test_Script/Error_Empty.json")
output=Logic_Manager.validate_file_empty_func(testfile3)
print(output+"\n")

testfile4="Test_Script/Error_Data_Format.json"
with open(testfile4, 'r') as file:
    data = json.load(file)
output=Logic_Manager.validate_resume_func(data)
print(output+"\n")

testfile5="Test_Script/Error_Missing_Keys.json"
with open(testfile5, 'r') as file:
    data = json.load(file)
output=Logic_Manager.validate_resume_keys_func(data)
print(output+"\n")