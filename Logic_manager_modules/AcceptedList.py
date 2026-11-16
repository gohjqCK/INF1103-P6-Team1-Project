from Logic_manager_modules.FilteredList import FilteredList
from Logic_manager_modules.Sort_score import Sort_score
from Logic_manager_modules.OfflineResume import OfflineResume
from Logic_manager_modules.OnlineResume import OnlineResume
#Format is accepted: [profile1],[profile2]
class AcceptedList(FilteredList,Sort_score):
  def __init__(self):
    super().__init__()

  #Abstract method #Formatting the resume before handing over to file manager.
  @property
  def output_dict(self) -> dict:
    return {"accepted":self.get_list_resume_dict}

  #Method to sort scores
  @property
  def sort_score(self) -> list[dict]:
    self.list.sort(key=lambda res: res.get_score, reverse=True)
    #sort_list= sorted(self.list, )
    return self.get_list_resume_dict
