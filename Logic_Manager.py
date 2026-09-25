import copy
##create a function that validate the ai outputs, handle errors
#might delete
def validate_AIOutput(ai_Output):
    ##AIOutput data type? type(AIOutput) == "list"
    ##Extract what? List of resumes ranked by business rules
    ##filter?
    print("Valid")
#might delete also
def structure_Output(ai_Output):
    ##structured as [name, age, Diploma, [KeyWords-softskills], [Keywords-skills]]
    print("Sturcutre")

#Remove name, age, gender andthing that can be discriminatory
def mask_Output(ai_Output):
    #Copies the data
    masked_data=copy.deepcopy(ai_Output)
    #initialise asign nuumber to each resume
    resume_Count=0
    #delete discriminatory identities and asign a number
    for resume in masked_data:
        for i in range(4):
            del resume[0]
        resume.insert(0,resume_Count)
        print(resume)
    return(masked_data)

def rank_Output(filtered_Output):
    #based on business rules?
    print("Rank")

#might delete
#Flag for Criminal Record
def record_holder(ai_Output):
    print("he bad")

#gather keywords
def gather_Keywords(stats_Copy):
    #initialise keywords [[keyword1,1],[keyword2,1],[keyword3,2]]
    keywords=[]
    for resume in stats_Copy:
        keywords=stats_Copy[3]  ##index depends on the position of the keyword
    print("Key")
    return(keywords)

#Resume Statistics rank which keywords are used most
def resume_stats(masked_AIOutput):
    #initialise stats
    stats_Copy=copy.deepcopy(masked_AIOutput)
    keyword_List=gather_Keywords(stats_Copy)
    print("End of statistics")
    return()


##Main workflow
#Output from AI
ai_Output=""
#initialise output
structured_AIOutput= structure_Output(ai_Output)
#masked output
masked_AIOutput=mask_Output(structured_AIOutput)

#Resume stats
output_stats=resume_stats(masked_AIOutput)

