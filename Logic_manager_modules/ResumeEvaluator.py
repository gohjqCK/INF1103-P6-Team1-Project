from Logic_manager_modules.Resume import Resume
class ResumeEvaluator:
  def __init__(self,resume):
    self.outcome = resume.get_outcome
    self.score = resume.get_score

  def category(self):
    if self.outcome != "scored" or not isinstance(self.score, float):
      return "invalid"
    if self.outcome == "scored" and self.score == 0.0:
      return "rejected"
    return "accepted"




