from Logic_manager_modules.AcceptedList import AcceptedList
from Logic_manager_modules.RejectedList import RejectedList
from Logic_manager_modules.InvalidList import InvalidList
class OverallList:
    def __init__(self):
        self.acceptedList=AcceptedList()
        self.rejectedList=RejectedList()
        self.invalidList=InvalidList()
    

    @property
    def get_accepted_list(self):
        return self.acceptedList
    
    @property
    def get_rejected_list(self):
        return self.rejectedList
    @property
    def get_invalid_list(self):
        return self.invalidList
    
    def add(self, resume, category: str):
        """Responsible ONLY for data management."""
        if category == "invalid":
            self.invalidList.list=resume
        elif category == "rejected":
            self.rejectedList.list=resume
        elif category == "accepted":
            self.acceptedList.list=resume




'''
list1=OverallList()
input1={"accepted":["lol"]}
input2={"rejecetd":["hehe"]}
input3={"invalid":["haha"]}
list1.list_overall=input1
list1.list_overall=input2
list1.list_overall=input3
print(list1.list_overall)
'''
