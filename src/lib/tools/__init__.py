from enum import Enum
import os
from typing import List, Type

import redis
from ...database.engine import SessionLocal
from ..platforms import Platform, platform_helper_factory
from ...globals import OAUTH_INTEGRATIONS
from .web_search import WebSearch, WebSearchConfig
from .report_generator import ReportGenerator, ReportGeneratorConfig
from .tool_maker import ToolMaker, ToolConfig
from .meets import MeetsHandler, MeetsConfig
from .google import GoogleOauthToolMaker, GoogleOauthConfig
from .jira import JiraConfig, JiraTools
from langchain.tools import Tool


class ToolName(Enum):
    WEB_SEARCH = "web_search"
    REPORT_GENERATOR = "report_generator"
    GOOGLE_MEETS = "google_meets"
    GOOGLE_OAUTH = "google_oauth"
    JIRA = "jira"


tool_name_to_cls: dict[ToolName, tuple[Type[ToolMaker], Type[ToolConfig]]] = {
    ToolName.WEB_SEARCH: (WebSearch, WebSearchConfig),
    ToolName.REPORT_GENERATOR: (ReportGenerator, ReportGeneratorConfig),
    ToolName.GOOGLE_MEETS: (MeetsHandler, MeetsConfig),
    ToolName.GOOGLE_OAUTH: (GoogleOauthToolMaker, GoogleOauthConfig),
    ToolName.JIRA: (JiraTools, JiraConfig)
}


def get_all_tools(
    toolnames_to_args: dict[ToolName, dict], platform: Platform, platform_args: dict
) -> List[Tool]:
    
    tools = []
    platform_helper = platform_helper_factory(platform, platform_args)
    for tool_name, args in toolnames_to_args.items():
        if tool_name not in tool_name_to_cls:
            continue

        tool_cls, tool_config_cls = tool_name_to_cls.get(tool_name)
        if tool_cls:
            oauth_integrations = {
                integration_name: OAUTH_INTEGRATIONS[integration_name]
                for integration_name in tool_cls.REQUESTED_OAUTH_INTEGRATIONS
            }
            tools.extend(
                tool_cls(
                    tool_config=tool_config_cls.model_validate(args),
                    oauth_integrations=oauth_integrations,
                    platform_helper=platform_helper,
                    session=SessionLocal(),
                    redis_client=redis.Redis.from_url(f"{os.getenv("REDIS_URL")}/3")
                ).create_ai_tools()
            )
    return tools
