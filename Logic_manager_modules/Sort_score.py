from abc import ABC, abstractmethod

class Sort_score(ABC):
    #Orders the list from highest to lowest score // using merge sort
    @abstractmethod
    def sort_score(self) -> list:
        pass