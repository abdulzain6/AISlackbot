from enum import Enum
from typing import List, Type
from .web_search import WebSearch
from .report_generator import ReportGenerator
from .tool_maker import ToolMaker
from langchain.tools import Tool

class ToolName(Enum):
    WEB_SEARCH = "web_search"
    REPORT_GENERATOR = "report_generator"

tool_name_to_cls: dict[ToolName, Type[ToolMaker]] = {
    ToolName.WEB_SEARCH: WebSearch,
    ToolName.REPORT_GENERATOR: ReportGenerator,
}

def get_all_tools(toolnames_to_args: dict[ToolName, dict]) -> List[Tool]:
    tools = []
    for tool_name, args in toolnames_to_args.items():
        tool_cls = tool_name_to_cls.get(tool_name)
        if tool_cls:
            tools.extend(tool_cls(**args).create_ai_tools())
    return tools