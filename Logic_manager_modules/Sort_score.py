from abc import ABC, abstractmethod
#interface to sort scores
class Sort_score(ABC):
    @abstractmethod
    def sort_score(self):
        pass