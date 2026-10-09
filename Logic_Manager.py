import copy
import json ##DELETE LTR
with open('results.json', 'r') as file:
    test_data = json.load(file)
'''test_data=[{ "file": "Entry Level IT Networking Resume.pdf","name": "","email": "","phone": "","outcome": "invalid","score": None,"reason": "Too long for one resume (26 pages)","summary": "",
   "skills": [],"qualifications": [],"work_experience": [],"projects": []}
   ] '''


'''variable resume only used in for loops'''

#function to remove personal info
def mask_resume_func(resume_dict):
    #Copies the data
    resume_list_copy=copy.deepcopy(resume_dict)
    filtered_outcome= filter_resume_func(resume_list_copy)
    filtered_resume=filtered_outcome[0]
    rejected_resume=filtered_outcome[1]
    #List of personal information to mask name, email, phone_number
    pi_list=["name","email", "phone"]
    #delete Personal info from every resume
    for resume in filtered_resume:
        #loops the pi list
        for item_key in pi_list:
            del resume[item_key]

    return([filtered_resume, rejected_resume])

#Remove invalid resumes and resumes that scored 0.0
def filter_resume_func(resume_list):
    rejected_list=[]
    for resume in resume_list:
        if resume["outcome"]=="invalid" or resume["score"]==0.0:
            rejected_list.append(resume)
            resume_list.remove(resume)
            continue
    return([resume_list,rejected_list])

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
    

##Statistics
#Resume Statistics rank which keywords are used most (Deciding what to do)
def resume_stats(masked_dictList):
    #Dictionary to store keywords (SoftSkills)
    keywords_dict={}
    for masked_resume in masked_dictList:
        softSkills_keyword=masked_resume["skills"]
        #adds into list if not found, or adds an increment to the value
        if softSkills_keyword not in keywords_dict:
            keywords_dict[softSkills_keyword]= 1
        else:
            keywords_dict[softSkills_keyword]+=1

    print("End of statistics")
    return(keywords_dict)



##Main workflow
#list of dictinary
#Output from AI
ai_output=""
#masked output
mask_result=mask_resume_func(test_data)
masked_filtered_resume= mask_result[0]
rejected_resume=mask_result[1]
print(masked_filtered_resume)
#sorted_resume= sort_resume_func(masked_filtered_resume)
#Resume stats
#output_stats=resume_stats(masked_dictList)
#print("\t", output_stats)

