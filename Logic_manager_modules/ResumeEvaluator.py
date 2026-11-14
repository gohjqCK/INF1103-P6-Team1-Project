from Logic_manager_modules.OnlineResume import OnlineResume
from Logic_manager_modules.OfflineResume import OfflineResume
from Logic_manager_modules.Resume import Resume
from Logic_manager_modules.OverallList import OverallList

#Create Resume or Profile
class ResumeEvaluator:
  #categorise the resume/profile into the respective list
  def evaluate(resume) -> str:
    """Responsible ONLY for business rules and categorization."""
    if resume.get_outcome != "scored" or not isinstance(resume.get_score, float):
      return "invalid"
    elif resume.get_outcome == "scored" and resume.get_score == 0.0:
      return "rejected"
    else:
      return "accepted"




