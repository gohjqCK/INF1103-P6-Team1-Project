from List import List
from FilterScore import FilterScore
class AcceptedList(List,FilterScore):
    def __init__(self,resume_list):
        super().__init__(resume_list)

    def outputList(self):
        return self.__resume_list