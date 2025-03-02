from enum import Enum
from typing import List, Type

from ...globals import OAUTH_INTEGRATIONS
from .web_search import WebSearch, WebSearchConfig
from .report_generator import ReportGenerator, ReportGeneratorConfig
from .tool_maker import ToolMaker, ToolConfig
from .meets import MeetsHandler, MeetsConfig
from .google import GoogleOauthToolMaker, GoogleOauthConfig
from langchain.tools import Tool
from ...database import DATABASE_HELPER_MAP
from ..platforms import Platform, platform_helper_factory


class ToolName(Enum):
    WEB_SEARCH = "web_search"
    REPORT_GENERATOR = "report_generator"
    GOOGLE_MEETS = "google_meets"
    GOOGLE_OAUTH = "google_oauth"


tool_name_to_cls: dict[ToolName, tuple[Type[ToolMaker], Type[ToolConfig]]] = {
    ToolName.WEB_SEARCH: (WebSearch, WebSearchConfig),
    ToolName.REPORT_GENERATOR: (ReportGenerator, ReportGeneratorConfig),
    ToolName.GOOGLE_MEETS: (MeetsHandler, MeetsConfig),
    ToolName.GOOGLE_OAUTH: (GoogleOauthToolMaker, GoogleOauthConfig),
}


def get_all_tools(
    toolnames_to_args: dict[ToolName, dict], platform: Platform, platform_args: dict
) -> List[Tool]:
    tools = []
    for tool_name, args in toolnames_to_args.items():
        if tool_name not in tool_name_to_cls:
            continue

        tool_cls, tool_config_cls = tool_name_to_cls.get(tool_name)
        if tool_cls:
            database_helpers = {
                helper: DATABASE_HELPER_MAP[helper]
                for helper in tool_cls.REQUESTED_DATABASE_HELPERS
            }

            oauth_integrations = {
                integration_name: OAUTH_INTEGRATIONS[integration_name]
                for integration_name in tool_cls.REQUESTED_OAUTH_INTEGRATIONS
            }
            tools.extend(
                tool_cls(
                    tool_config=tool_config_cls.model_validate(args),
                    database_helpers=database_helpers,
                    oauth_integrations=oauth_integrations,
                    platform_helper=platform_helper_factory(platform, platform_args),
                ).create_ai_tools()
            )
    return tools
