from Abstract.FilteredList import FilteredList
from Interface.Output_dict import Output_dict
from Interface.Sort_score import Sort_score
#from Resume import Resume
#Format is accepted: [profile1],[profile2]
class AcceptedList(FilteredList,Output_dict,Sort_score):
    def __init__(self):
        super().__init__()
    #Abstract method
    @property
    def output_dict(self):
        return {"accepted":self.list_to_profile}

    @property
    def sort_score(self):
        self.list.sort(key=lambda res: res.get_score, reverse=True)
        #sort_list= sorted(self.list, )
        return self.list_to_profile

##Test data

'''
list1=AcceptedList()
list1.list=Resume("Hakimfile","Hakim","Hakim@email.com",99922229,"Scored",50,"Meets 1 of 2","SummaryView","Python","Qualificaiton","Work Experience","Projects")
list1.list=Resume("CYfile","Hakim","Hakim@email.com",99922229,"Scored",75,"Meets 1 of 2","SummaryView","Debian","Qualificaiton","Work Experience","Projects")
list1.list=Resume("Hakimfile","Hakim","Hakim@email.com",99922229,"Scored",12,"Meets 1 of 2","SummaryView","C++","Qualificaiton","Work Experience","Projects")

print(list1.sort_score)
print(list1.output_dict)
'''