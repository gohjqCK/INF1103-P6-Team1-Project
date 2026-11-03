class OverallList:
    def __init__(self):
        self.__filtered_list=[]
    
    @property
    def list_overall(self):
        return self.__filtered_list

    @list_overall.setter
    def list_overall(self,item):
        self.__filtered_list.append(item)




'''
list1=OverallList()
input1={"accepted":["lol"]}
input2={"rejecetd":["hehe"]}
input3={"invalid":["haha"]}
list1.list_overall=input1
list1.list_overall=input2
list1.list_overall=input3
print(list1.list_overall)
'''
