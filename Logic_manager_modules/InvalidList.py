from Logic_manager_modules.FilteredList import FilteredList
from Logic_manager_modules.OnlineResume import Resume
class InvalidList(FilteredList):
    def __init__(self):
        super().__init__()

    #Abstract method
    @property
    def output_dict(self):
        return {"invalid":self.list_to_profile}


