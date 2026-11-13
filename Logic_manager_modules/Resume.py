from abc import ABC, abstractmethod
class Resume(ABC):
    def __init__(self,resume_dict:dict):
        self.__file=resume_dict["file"]
        self.__outcome=resume_dict["outcome"]
        self.__reason=resume_dict["reason"]
        self.__score=resume_dict["score"]
        self.__status=None
        self.__pages=None
        self.__text=None

    @property
    def get_file(self) -> str:
        return self.__file
    @property
    def get_outcome(self) -> str:
        return self.__outcome

    @property
    def get_reason(self) -> str:
        return self.__reason
    
    @property
    def get_score(self) -> float:
        return self.__score
        
    @property
    def status(self) -> str:
        return self.__status
    
    @status.setter
    def status(self,status):
        self.__status=status

    @property
    def pages(self) -> int:
        return self.__pages

    @pages.setter
    def pages(self,pages):
        self.__pages=pages

    @property
    def text(self) -> str:
        return self.__text

    @text.setter
    def text(self,text):
        self.__text=text
    
    @abstractmethod
    def get_resume():
        pass
    
