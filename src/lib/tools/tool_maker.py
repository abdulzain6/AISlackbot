from abc import ABC, abstractmethod
from langchain_core.tools import Tool
from pydantic import BaseModel


class ToolConfig(BaseModel):
    ...

class ToolMaker(ABC):
    @abstractmethod
    def __init__(self, tool_config: ToolConfig = None):
        ...

    @abstractmethod
    def create_ai_tools(self) -> list[Tool]:
        ...