from Logic_manager_modules.FilteredList import FilteredList
from Logic_manager_modules.OnlineResume import Resume
class RejectedList(FilteredList):
    def __init__(self):
        super().__init__()
    
    #Abstract method #Formatting the resume before handing over to file manager.
    @property
    def output_dict(self) -> dict:
        return {"rejected":self.get_list_resume_dict}


