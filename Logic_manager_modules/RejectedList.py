from Logic_manager_modules.FilteredList import FilteredList
from Logic_manager_modules.Resume import Resume
class RejectedList(FilteredList):
    def __init__(self):
        super().__init__()
        
    #Abstract method
    @property
    def output_dict(self):
        return {"rejected":self.list_to_profile}


