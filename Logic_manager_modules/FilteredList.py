from Logic_manager_modules.OfflineResume import OfflineResume
from abc import ABC, abstractmethod

class FilteredList(ABC):
    def __init__(self):
        self.__resume_list=[]

    @property
    def show_profiles(self):
        profile_list=[]
        for profile in self.__resume_list:
            profile_contents=profile.get_resume
            profile_list.append(profile_contents)
            return profile_list

    #prints list
    @property
    def list(self):
        return self.__resume_list
    
    #adds to list usage
    @list.setter
    def list(self,resume):
        self.__resume_list.append(resume)

    @abstractmethod
    def output_dict(self):
        pass

    #Concrete Method
    @property
    def list_to_profile(self):
        profile_list=[]
        for resume in self.list:
            profile_list.append(resume.get_resume)
        return profile_list
