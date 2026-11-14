from Logic_manager_modules.OnlineResume import OnlineResume
from Logic_manager_modules.OfflineResume import OfflineResume
from Logic_manager_modules.OverallList import OverallList

#Create Resume or Profile
class ResumeEvaluator:
  
  #categorise the resume/profile into the respective list
  def allocate(overallList,resume):
    if resume.get_outcome != "scored" or not isinstance(resume.get_score, float):
      overallList.list_overall[2].list=resume
    elif resume.get_outcome == "scored" and resume.get_score == 0.0:
      overallList.list_overall[1].list=resume
    else:
      overallList.list_overall[0].list=resume





