from Logic_manager_modules.OfflineResume import OfflineResume
from abc import ABC, abstractmethod

class FilteredList(ABC):
    def __init__(self):
        self.__resume_list=[]

    #Concrete Method (all child classes will inherit this)
    #Formatting: returns all resume information (in a dictionary) into a list for other operations.
    @property
    def get_list_resume_dict(self) -> list[dict]:
        profile_list=[]
        for profile in self.__resume_list:
            profile_contents=profile.get_resume
            profile_list.append(profile_contents)
            return profile_list

    #prints list of resumes class
    @property
    def list(self) -> list:
        return self.__resume_list
    
    #adds resume to list.
    @list.setter
    def list(self,resume):
        self.__resume_list.append(resume)

    #Formatting the resume before handing over to file manager.
    @abstractmethod
    def output_dict(self):
        pass
