'''Logic_Manager Library'''
import copy
import json
from pathlib import Path
from json.decoder import JSONDecodeError
from Logic_manager_modules.Resume import Resume
from Logic_manager_modules.Profile import Profile
from Logic_manager_modules.OverallList import OverallList
from Logic_manager_modules.AcceptedList import AcceptedList
from Logic_manager_modules.RejectedList import RejectedList
from Logic_manager_modules.InvalidList import InvalidList
from Logic_manager_modules.ResumeEvaluator import ResumeEvaluator

'''===========Logic_Manager Rules:=================
    variable resume only used in for loops
    _func are functions to be called'''
    

#prints error detected
def print_err_detected():
    print("Error detected:")

#prints successful operation
def print_success():
    print("Sucessfully executed")

#Checks if file exists
def validate_file_exists_func(file_path):
    if file_path.is_file():
        return 0
    else:
        return"LM: The file does not exist. Either AI Output wrong file name or did not output at all"

#Checks if file is json type
def validate_file_type_func(file_path):
    if file_path.suffix.lower()==".json":
        return(0)
    else:
        return "LM: AI output wrong file type"


#Checks if json file is empty
def validate_file_empty_func(file_path):
    try:
        with open(file_path, 'r') as file:
            data = json.load(file)
        if not data: 
            return "LM: The file contains an empty JSON object or array ({ or [])."
        else:
            return 0
    except JSONDecodeError:
        # This catches completely blank files or files with malformed JSON
        return "LM: The file is completely empty or contains invalid JSON."

#Validate data type of resume list
def validate_resume_func(resume_list):
    #expected data type:List
    resume_data_type=(type(resume_list))
    if resume_data_type is list:
        print("LM: Correct Outer data type")
    else:
        err_msg="LM: AI did not print out correct data type.\n" \
                 f"Expected data type <class 'list'>. Data type received: {resume_data_type}"
        return err_msg
    resume_count=0
    for resume in resume_list:
        if type(resume) is not dict:
            err_msg="Resume in "+ str(resume_count) +" position is not dictionary"
            return err_msg
    return 0

#Check if keys exists: "outcome" and "score"
def validate_resume_keys_func(resume_list):
    result=""
    resume_count=0
    for resume in resume_list:
        if "outcome" not in resume:
            result= "dictionary in "+ str(resume_count) +" position is missing a key named \"outcome\""

        if "score" not in resume:
            result= "dictionary in "+ str(resume_count)+" position is missing a key named \"score\""
            break
        resume_count+=1
    return result

def combined_list_func():
    return {"acceptedList":[],"rejectedList":[],"invalidList":[]}

def create_classes(combinedList):

    #creating classes
    acceptedList=AcceptedList()
    rejectedList=RejectedList()
    invalidList=InvalidList()
    #assign list
    
    acceptedList.list=combinedList["acceptedList"]
    rejectedList.list=combinedList["rejectedList"]
    invalidList.list=combinedList["invalidList"]

    return acceptedList,rejectedList,invalidList


#Remove invalid resumes and resumes that scored 0.0
def filter_resume_online_func(resume_list):
    #Copies the data
    resume_list_copy=copy.deepcopy(resume_list)
    #to allocate stringname
    combinedList=combined_list_func()
    for raw_resume in resume_list_copy:
        #create a resume
        resume= Resume(raw_resume)
        #Decide which list to put the resume in
        resumeEvaluate=ResumeEvaluator(resume)
        #the return value + "List"
        stringname=str(resumeEvaluate.category())+"List"
        
        combinedList[stringname].append(resume)
    #creating classes
    return create_classes(combinedList)

def filter_resume_offline_func(resume_list):
    #Copies the data
    resume_list_copy=copy.deepcopy(resume_list)
    combinedList=combined_list_func()
    for raw_resume in resume_list_copy:
        #Create a profile(offline resume)
        profile=Profile(raw_resume)
        #Decide which list to put the resume in
        profileEvaluate=ResumeEvaluator(profile)
        stringname=str(profileEvaluate.category())+"List"
        combinedList[stringname].append(profile)
    return create_classes(combinedList)

'''def filter_resume_func(resume_list,mode):
    function_name=f"filter_resume_{mode}_func"
    function_name.__name__'''


def offline_screening_func(resume_list, rules):
    for resume in resume_list:
        resume_text = resume.get("text", "").lower()
        matched_count = 0
        total_rules = len(rules)

        for rule in rules:
            rule_text = rule.get("text", "").lower()
            words = [w for w in rule_text.split() if len(w) > 3]
            if words and any(word in resume_text for word in words):
                matched_count += 1

        if matched_count > 0:
            resume["outcome"] = "scored"
            resume["score"] = round((matched_count / total_rules) * 100.0, 1)
            resume["reason"] = f"Matched {matched_count} out of {total_rules} rules"
        else:
            resume["outcome"] = "scored"
            resume["score"] = 0.0
            resume["reason"] = "No rules matched"
    return resume_list


def validateOfflineFile(results_path):
    offlinefile=validate_file_exists_func(results_path)
    if  offlinefile != 0:
        return offlinefile
    offlinefile=validate_file_type_func(results_path)
    if  offlinefile!= 0:
        return offlinefile
    offlinefile=validate_file_empty_func(results_path)
    if  offlinefile!= 0:
        return offlinefile
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    offlinedata=validate_resume_func(data)
    if offlinedata != 0:
        print(offlinedata)
        return offlinedata
    offlinedata=validate_resume_keys_func(data)
    if offlinedata != "":
        print(offlinedata)
        return offlinedata
    return 0