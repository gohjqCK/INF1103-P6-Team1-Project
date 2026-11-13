from Logic_manager_modules.Resume import Resume
class OnlineResume(Resume):
    def __init__(self,resume_dict:dict):
        super().__init__(resume_dict)
        self.__name=resume_dict["name"]
        self.__email=resume_dict["email"]
        self.__phone=resume_dict["phone"]
        self.__summary=resume_dict["summary"]
        self.__skills=resume_dict["skills"]
        self.__qualifications=resume_dict["qualifications"]
        self.__work_experience=resume_dict["work_experience"]
        self.__projects=resume_dict["projects"]
    @property
    def get_resume(self):
        return {"name":self.__name,"email":self.__email,"phone":self.__phone,"summary":self.__summary,"skills":self.__skills,"qualifications":self.__qualifications,"work_experience":self.__work_experience,"projects":self.__projects,"file":self.get_file,"status":self.status,"reason":self.get_reason,"pages":self.pages,"text":self.text,"outcome":self.get_outcome,"score":self.get_score}

    @property
    def get_name(self):
        return self.__name
    @property
    def get_email(self):
        return self.__email
    @property
    def get_phone(self):
        return self.__phone
    @property
    def get_summary(self):
        return self.__summary
    @property
    def get_skills(self):
        return self.__skills
    @property
    def get_qualifications(self):
        return self.__qualifications
    @property
    def get_work_experience(self):
        return self.__work_experience
    @property
    def get_projects(self):
        return self.__projects