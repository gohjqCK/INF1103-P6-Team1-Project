#interface that output list as dictionary
from abc import ABC, abstractmethod
class Output_dict(ABC):
    @abstractmethod
    def output_dict(self):
        pass