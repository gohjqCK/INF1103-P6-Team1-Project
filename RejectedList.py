from FilteredList import FilteredList
from Output_dict import Output_dict
from Resume import Resume
class RejectedList(FilteredList,Output_dict):
    def __init__(self):
        super().__init__()

    @property
    def show_profiles(self):
        profile_list=[]
        for profile in self.__resume_list:
            profile_contents=profile.get_profile
            profile_list.append(profile_contents)
        return profile_list
    
    @property
    def list(self):
        return self.__resume_list
    
    @list.setter
    def list(self,resume):
        self.__resume_list=resume
        
    #Abstract method
    @property
    def output_dict(self):
        return {"rejected":self.list_to_profile}


