from abc import ABC, abstractmethod

class FilteredList(ABC):
    def __init__(self):
        self.__resume_list=[]

    #prints list
    @property
    @abstractmethod
    def list(self):
        return self.__resume_list
    
    #adds to list usage (listname.list=resume)
    @list.setter
    @abstractmethod
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
            profile_list.append(resume.get_profile)
        return profile_list
