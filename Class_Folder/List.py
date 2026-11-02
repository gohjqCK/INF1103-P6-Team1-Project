from abc import ABC, abstractmethod

class List(ABC):
    def __init__(self,resume_list):
        self.__resume_list=resume_list

    @abstractmethod
    def outputList(self):
        return self.__resume_list

    def get_filtered_resume_list(self):
        pass
        resume_list=self.__resume_list
        #for resume in resume_list:
            #status=