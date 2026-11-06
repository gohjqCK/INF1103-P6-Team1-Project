from Logic_manager_modules.Profile import Profile
class Resume:
    def __init__(self,resume_dict):
        self.__name=resume_dict["name"]
        self.__email=resume_dict["email"]
        self.__phone=resume_dict["phone"]
        self.__summary=resume_dict["summary"]
        self.__skills=resume_dict["skills"]
        self.__qualifications=resume_dict["qualifications"]
        self.__work_experience=resume_dict["work_experience"]
        self.__projects=resume_dict["projects"]
        self.__profile=Profile({"file":resume_dict["file"],"outcome": resume_dict["outcome"],"reason":resume_dict["reason"],"score":resume_dict["score"]})
    @property
    def get_resume(self):
        return {"name":self.__name,"email":self.__email,"phone":self.__phone,"summary":self.__summary,"skills":self.__skills,"qualifications":self.__qualifications,"work_experience":self.__work_experience,"projects":self.__projects}
    @property
    def get_profile(self):
        profile_dict=self.__profile.get_profile
        return profile_dict
    @property
    def get_score(self):
        return self.__profile.get_score
    @property
    def get_outcome(self):
        return self.__profile.get_outcome
    @property
    def get_reason(self):
        return self.__profile.get_reason
    