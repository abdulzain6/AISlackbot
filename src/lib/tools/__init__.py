from enum import Enum
from typing import List, Type
from .web_search import WebSearch, WebSearchConfig
from .report_generator import ReportGenerator, ReportGeneratorConfig
from .tool_maker import ToolMaker, ToolConfig
from .task_tools import TaskTools, TasksConfig
from .meets import MeetsHandler, MeetsConfig
from .google import GoogleOauthToolMaker, GoogleOauthConfig
from langchain.tools import Tool


class ToolName(Enum):
    WEB_SEARCH = "web_search"
    REPORT_GENERATOR = "report_generator"
    TEAM_TASKS = "team_tasks"
    GOOGLE_MEETS = "google_meets"
    GOOGLE_OAUTH = "google_oauth"


tool_name_to_cls: dict[ToolName, tuple[Type[ToolMaker], Type[ToolConfig]]] = {
    ToolName.WEB_SEARCH: (WebSearch, WebSearchConfig),
    ToolName.REPORT_GENERATOR: (ReportGenerator, ReportGeneratorConfig),
    ToolName.TEAM_TASKS: (TaskTools, TasksConfig),
    ToolName.GOOGLE_MEETS: (MeetsHandler, MeetsConfig),
    ToolName.GOOGLE_OAUTH: (GoogleOauthToolMaker, GoogleOauthConfig),
}


def get_all_tools(toolnames_to_args: dict[ToolName, dict]) -> List[Tool]:
    tools = []
    for tool_name, args in toolnames_to_args.items():
        if tool_name not in tool_name_to_cls:
            continue
        
        tool_cls, tool_config_cls = tool_name_to_cls.get(tool_name)
        if tool_cls:
            tools.extend(
                tool_cls(
                    tool_config=tool_config_cls.model_validate(args)
                ).create_ai_tools()
            )
    return tools
