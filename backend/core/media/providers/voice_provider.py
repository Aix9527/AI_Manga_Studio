"""Voice Production OS · Provider 抽象（GPT 设计）"""
from abc import ABC, abstractmethod



class VoiceProvider(ABC):
    """
    统一 VoiceProvider 接口

    - generate: 文本 → 语音
    - clone:    参考音频 → 角色声音资产
    - health:   引擎可用性
    """

    name = ""


    @abstractmethod
    def generate(
        self,
        request
    ):
        pass


    @abstractmethod
    def clone(
        self,
        request
    ):
        pass


    @abstractmethod
    def health(self):
        pass
