from List import List

class InvalidList(List):
    def __init__(self,resume_list):
        super().__init__(resume_list)

    def outputList(self):
            return self.__resume_list