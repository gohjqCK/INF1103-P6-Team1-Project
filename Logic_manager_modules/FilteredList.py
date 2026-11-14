from Logic_manager_modules.OfflineResume import OfflineResume
from abc import ABC, abstractmethod

class FilteredList(ABC):
    def __init__(self):
        self.__resume_list=[]

    #Concrete Method
    @property
    def get_list_resume_dict(self) -> list[dict]:
        profile_list=[]
        for profile in self.__resume_list:
            print(profile)
            profile_contents=profile.get_resume
            profile_list.append(profile_contents)
        return profile_list

    #prints list
    @property
    def list(self) -> list:
        return self.__resume_list
    
    #adds to list usage
    @list.setter
    def list(self,resume):
        self.__resume_list.append(resume)

    @abstractmethod
    def output_dict(self):
        pass
