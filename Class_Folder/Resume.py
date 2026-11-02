class Resume():
    def __init__(self,file,status,reason,pages,text,outcome,score):
        self.__filename=file
        self.__status=status
        self.__reason=reason
        self.__pages=pages
        self.__text=text
        self.__outcome=outcome
        self.__score=score

    def get_status(self):
        return self.__status
    def get_reason(self):
        return self.__reason
    def get_text(self):
        return self.__text
    def get_outcome(self):
        return self.__outcome
    def get_score(self):
        return self.__score