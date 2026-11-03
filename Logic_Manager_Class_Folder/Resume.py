from Profile import Profile
class Resume:
    def __init__(self,file,name,email,phone,outcome,score,reason,summary,skills,qualifications,work_experience,projects):
        self.__name=name
        self.__email=email
        self.__phone=phone
        self.__summary=summary
        self.__skills=skills
        self.__qualifications=qualifications
        self.__work_experience=work_experience
        self.__projects=projects
        self.__profile=Profile(file,outcome,reason,score)
    @property
    def get_resume(self):
        return {"name":self.__name,"email":self.__email,"phone":self.__phone,"summary":self.__summary,"skills":self.__skills,"qualifications":self.__qualifications,"work_experience":self.__work_experience,"projects":self.__projects}
    @property
    def get_profile(self):
        profile_dict=self.__profile.get_profile_dict
        return profile_dict
    @property
    def get_score(self):
        return self.__profile.score
    

