import copy
#Expected input resume_list =[{},{},{}] List of dictionary (for test script)
test_data=[{"name":"Sarah","email":"sarah@gmail.com","phone_number":"99128291","address":"Tampines East","Diploma":"Cybersecurity","CGPA":3.0,"SoftSkills":"Teamwork","ID":1},
           {"name":"Ben","email":"ben@gmail.com","phone_number":"82919912","address":"Bedok North","Diploma":"Information Security","CGPA":3.5,"SoftSkills":"Adaptability","ID":2},
           {"name":"Shawn","email":"shawn@gmail.com","phone_number":"91289291","address":"Bedok South","Diploma":"Desgin Engineering","CGPA":4.0,"SoftSkills":"Problem-Solving","ID":3},
           {"name":"Emily","email":"emily@gmail.com","phone_number":"92349291","address":"Jurong West","Diploma":"Desgin Engineering","CGPA":3.7,"SoftSkills":"Problem-Solving","ID":4}]

#function to remove personal info

def mask_Resume(resume_Dict):
    #Copies the data
    masked_data=copy.deepcopy(resume_Dict)
    #List of personal information to mask name, email, phone_number, address
    pi_List=["name","email", "phone_number","address"]
    #delete Personal info from every resume
    for resume in masked_data:
        #loops the pi list
        for item_key in pi_List:
            del resume[item_key]

    return(masked_data)

##Statistics
#gather keywords

#Resume Statistics rank which keywords are used most
def resume_Stats(masked_DictList):
    #Dictionary to store keywords (SoftSkills)
    keywords_Dict={}
    for masked_resume in masked_DictList:
        softSkills_Keyword=masked_resume["SoftSkills"]
        #adds into list if not found, or adds an increment to the value
        if softSkills_Keyword not in keywords_Dict:
            keywords_Dict[softSkills_Keyword]= 1
        else:
            keywords_Dict[softSkills_Keyword]+=1

    print("End of statistics")
    return(keywords_Dict)



##Main workflow
#list of dictinary
#Output from AI
ai_Output=""
#masked output
masked_DictList=mask_Resume(test_data)

#Resume stats
output_stats=resume_Stats(masked_DictList)
print("\t", output_stats)

