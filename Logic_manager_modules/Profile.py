#Contents that will be shown in terminal
class Profile:
    def __init__(self,profile_dict):
        self.__file=profile_dict["file"]
        self.__outcome=profile_dict["outcome"]
        self.__reason=profile_dict["reason"]
        self.__score=profile_dict["score"]
        self.__status=None
        self.__pages=None
        self.__text=None

    @property
    def status(self):
        return self.__status
    
    @status.setter
    def status(self,status):
        self.__status=status

    @property
    def pages(self):
        return self.__pages

    @pages.setter
    def pages(self,pages):
        self.__pages=pages

    @property
    def text(self):
        return self.__text

    @text.setter
    def text(self,text):
        self.__text=text

    @property
    def get_outcome(self):
        return self.__outcome
    
    @property
    def get_score(self):
        return self.__score
    
    @property
    def get_reason(self):
        return self.__reason

    @property
    def get_profile(self):
        return {"file":self.__file,"status":self.__status,"reason":self.__reason,"pages":self.__pages,"text":self.__text,"outcome":self.__outcome,"score":self.__score}