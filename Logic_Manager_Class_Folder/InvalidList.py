from Abstract.FilteredList import FilteredList
from Interface.Output_dict import Output_dict
from Resume import Resume
class InvalidList(FilteredList,Output_dict):
    def __init__(self):
        super().__init__()
    #Abstract method
    @property
    def output_dict(self):
        return {"invalid":self.list_to_profile}


