#Contents that will be shown in terminal
class Profile:
    def __init__(self,file,outcome,reason,score):
        self.__file=file
        self.__outcome=outcome
        self.__reason=reason
        self.__score=score
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
    def outcome(self):
        return self.__outcome
    
    @property
    def score(self):
        return self.__score
    
    @property
    def reason(self):
        return self.__reason
    @property
    def get_profile_dict(self):
        return {"file":self.__file,"status":self.__status,"reason":self.__reason,"pages":self.__pages,"text":self.__text,"outcome":self.__outcome,"score":self.__score}

