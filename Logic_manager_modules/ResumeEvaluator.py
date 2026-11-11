from Logic_manager_modules.Resume import Resume
from Logic_manager_modules.Profile import Profile
from Logic_manager_modules.OverallList import OverallList
from Logic_manager_modules.AcceptedList import AcceptedList
from Logic_manager_modules.RejectedList import RejectedList
from Logic_manager_modules.InvalidList import InvalidList

#Create Resume or Profile
class ResumeEvaluator:
  def __init__(self,resume_list:list,obj_type:object):
    self._resume_list=resume_list
    self._obj_type=obj_type
    self._overall_list=OverallList()

  def create_classes(self):
    acceptedList=AcceptedList()
    rejectedList=RejectedList()
    invalidList=InvalidList()
    self._overall_list.list_overall=acceptedList
    self._overall_list.list_overall=rejectedList
    self._overall_list.list_overall=invalidList
    
  #creates resume or profile(for offline mode)
  def create_obj(self):
    for raw_resume in self._resume_list:
      resume=self._obj_type(raw_resume)
      self.allocate(resume)

  #categorise the resume/profile into the respective list
  def allocate(self,resume):
    if resume.get_outcome != "scored" or not isinstance(resume.get_score, float):
      self._overall_list.list_overall[2].list=resume
    elif resume.get_outcome == "scored" and resume.get_score == 0.0:
      self._overall_list.list_overall[1].list=resume
    else:
      self._overall_list.list_overall[0].list=resume





