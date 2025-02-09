from abc import ABC, abstractmethod
from langchain_core.tools import Tool

class ToolMaker(ABC):
    @abstractmethod
    def create_ai_tools(self) -> list[Tool]:
        ...