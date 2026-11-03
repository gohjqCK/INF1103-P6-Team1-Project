class ResultsData:
    def __init__(self,results_data):
        self.__results_data=results_data

    #Validate data type of resume list
    def validate_resume_func(self):
        #expected data type:List
        resume_data_type=(type(self.__results_data))
        if resume_data_type is list:
            print("LM: Correct Outer data type")
        else:
            err_msg="LM: AI did not print out correct data type.\n" \
                    f"Expected data type <class 'list'>. Data type received: {resume_data_type}"
            return err_msg
        resume_count=0
        for resume in self.__results_data:
            if type(resume) is not dict:
                err_msg="Resume in "+ str(resume_count) +" position is not dictionary"
                return err_msg
        return 0

    #Check if keys exists: "outcome" and "score"
    def validate_resume_keys_func(self):
        result=""
        resume_count=0
        for resume in self.__results_data:
            if "outcome" not in resume:
                result= "dictionary in "+ str(resume_count) +" position is missing a key named \"outcome\""

            if "score" not in resume:
                result= "dictionary in "+ str(resume_count)+" position is missing a key named \"score\""
                break
            resume_count+=1
        return result