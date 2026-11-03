from Abstract.FilteredList import FilteredList
from Interface.Output_dict import Output_dict
from Resume import Resume
class RejectedList(FilteredList,Output_dict):
    def __init__(self):
        super().__init__()
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


