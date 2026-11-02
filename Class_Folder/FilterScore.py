from abc import ABC, abstractmethod

'''#Remove invalid resumes and resumes that scored 0.0
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
    return sorted_resume_list'''