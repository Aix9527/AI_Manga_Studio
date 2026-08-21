from abc import ABC, abstractmethod



class ProviderAdapter(ABC):


    name=""


    @abstractmethod
    def validate(
        self,
        request
    ):
        pass



    @abstractmethod
    def estimate(
        self,
        request
    ):
        pass



    @abstractmethod
    def generate(
        self,
        request
    ):
        pass
