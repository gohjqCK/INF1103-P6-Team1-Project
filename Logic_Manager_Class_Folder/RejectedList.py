from Abstract.FilteredList import FilteredList
from Interface.Output_dict import Output_dict
from Resume import Resume
class RejcetedList(FilteredList,Output_dict):
    def __init__(self):
        super().__init__()
    #Abstract method
    @property
    def output_dict(self):
        return {"rejected":self.list_to_profile}


