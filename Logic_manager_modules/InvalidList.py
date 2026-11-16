from Logic_manager_modules.FilteredList import FilteredList
from Logic_manager_modules.OnlineResume import Resume
class InvalidList(FilteredList):
    def __init__(self):
        super().__init__()

    #Formatting the resume before handing over to file manager.
    #Abstract method
    @property
    def output_dict(self) -> dict:
        return {"invalid":self.get_list_resume_dict}


