#Contents that will be shown in terminal
from Logic_manager_modules.Resume import Resume
class OfflineResume(Resume):
    def __init__(self,resume_dict:dict):
        super().__init__(resume_dict)

    @property
    def get_resume(self):
        return {"file":self.get_file,"status":self.status,"reason":self.get_reason,"pages":self.pages,"text":self.text,"outcome":self.get_outcome,"score":self.get_score}
