from main_modules.MainProg import MainProg
from Logic_manager_modules import Logic_Manager as LogicManager
##AI Sample output

##Example resume class
class hardcopy():
    def __init__(self):
        pass
#Empty LIST
results=[]
accepted, rejected,invalid = MainProg._categorise(results,True)

#Missing keys
results= [{"name":"Hakim"}]
accepted, rejected,invalid = MainProg._categorise(results,True)

resumeType=hardcopy()

#Wrong Resume type
accepted, rejected,invalid=LogicManager.filter_resume_func(results,resumeType)