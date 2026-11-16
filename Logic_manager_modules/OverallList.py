from Logic_manager_modules.AcceptedList import AcceptedList
from Logic_manager_modules.RejectedList import RejectedList
from Logic_manager_modules.InvalidList import InvalidList
class OverallList:
    def __init__(self):
        self.acceptedList=AcceptedList()
        self.rejectedList=RejectedList()
        self.invalidList=InvalidList()
    
    #each method returns the respective list
    @property
    def get_accepted_list(self)->list:
        return self.acceptedList
    @property
    def get_rejected_list(self)->list:
        return self.rejectedList
    @property
    def get_invalid_list(self)->list:
        return self.invalidList

    #Method to link a resume to the category list.
    def add(self, resume, category: str)-> None:
        """Responsible ONLY for data management."""
        if category == "invalid":
            self.invalidList.list=resume
        elif category == "rejected":
            self.rejectedList.list=resume
        elif category == "accepted":
            self.acceptedList.list=resume


