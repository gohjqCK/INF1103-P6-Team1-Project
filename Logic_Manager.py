'''Logic_Manager Library'''
import copy
import json
from json.decoder import JSONDecodeError
from pathlib import Path

'''===========Logic_Manager Rules:=================
    variable resume only used in for loops
    _func are functions to be called'''

class ResumeList():
    def __init__(self,resume_list):
        self.__resume_list=resume_list

    def get_score_list(self):
        score_list=[]
        resume_list=self.__resume_list
        for resume in resume_list:
            score_list.append(resume.get_score())
        return score_list

    def get_filtered_resume_list(self):
        pass
        resume_list=self.__resume_list
        #for resume in resume_list:
            #status=

class AcceptedList():
    def __init__(self,resume_list):
        self.__resume_list=resume_list

class RejcetedList():
    def __init__(self,resume_list):
        self.__resume_list=resume_list

class InvalidList():
    def __init__(self,resume_list):
        self.__resume_list=resume_list

class Resume():
    def __init__(self,file,status,reason,pages,text,outcome,score):
        self.__filename=file
        self.__status=status
        self.__reason=reason
        self.__pages=pages
        self.__text=text
        self.__outcome=outcome
        self.__score=score

    def get_status(self):
        return self.__status
    def get_reason(self):
        return self.__reason
    def get_text(self):
        return self.__text
    def get_outcome(self):
        return self.__outcome
    def get_score(self):
        return self.__score
    

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

#Remove invalid resumes and resumes that scored 0.0
def filter_resume_func(resume_list):
    #Copies the data
    resume_list_copy=copy.deepcopy(resume_list)
    invalid_list=[]
    rejected_list=[]
    filtered_list=[]
    for resume in resume_list_copy:
        if resume["outcome"]!="scored" or type(resume["score"]) is not float:
            invalid_list.append(resume)
            continue
        elif resume["outcome"]=="scored" and resume["score"]==0.0:
            rejected_list.append(resume)
            continue
        else:
            filtered_list.append(resume)
            
    return [filtered_list,rejected_list,invalid_list]

#Orders the list from highest to lowest score // using merge sort
def sort_resume_func(resume_list):
    score_list=extract_scores_func(resume_list)
    sorted_scores=sort_score_func(score_list)
    sorted_resume_list=link_score_to_list_func(sorted_scores, resume_list)
    return sorted_resume_list


#Extract scores of resumes
def extract_scores_func(resume_list):
    score_list=[]
    for resume in resume_list:
        dictionary_value=resume["score"]
        score_list.append(dictionary_value)
    return score_list

#Merge sort scores
def sort_score_func(score_list):
    # Base case: A list of zero or one elements is already sorted
    if len(score_list) <= 1:
        return score_list
    
    # Divide: Split the array into two halves
    mid = len(score_list) // 2
    left_half = score_list[:mid]
    right_half = score_list[mid:]
    
    # Conquer: Recursively sort both halves
    sorted_left = sort_score_func(left_half)
    sorted_right = sort_score_func(right_half)
    
    # Merge: Combine the sorted halves
    return merge(sorted_left, sorted_right)

def merge(left, right):
    result = []
    i = j = 0
    # Compare elements from both parts and build the sorted list
    while i < len(left) and j < len(right):
        if left[i] > right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    # Append any remaining elements left over from either list
    result.extend(left[i:])
    result.extend(right[j:])
    return result

def link_score_to_list_func(sorted_scores, resume_list):
    for resume in resume_list:
        #finds the value of score in loop resume
        resume_score=resume["score"]
        #finds the index of the score on the sorted list
        index_position= sorted_scores.index(resume_score)
        #Replace the sorted score with the resume
        sorted_scores[index_position]=resume
    return sorted_scores

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