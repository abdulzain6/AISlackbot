import redis
import os

from typing import List, Optional, Type
from enum import Enum

from ..platforms.platform_helper import PlatformHelper
from .presentations import PresentationToolMaker, PresentationMakerConfig
from .uml_diagram_maker import AIPlantUMLGenerator
from ...database.engine import SessionLocal
from ..platforms import Platform, platform_helper_factory
from ...globals import OAUTH_INTEGRATIONS
from .web_search import WebSearch, WebSearchConfig
from .report_generator import ReportGenerator, ReportGeneratorConfig
from .tool_maker import ToolMaker, ToolConfig
from .meets import MeetsHandler, MeetsConfig
from .google import GoogleOauthToolMaker, GoogleOauthConfig
from .jira import JiraConfig, JiraTools
from .image_generator import ImageGenerator, ImageGeneratorConfig
from .rag import RAGToolConfig, RAGToolMaker
from langchain.tools import Tool, BaseTool


class ToolName(Enum):
    WEB_SEARCH = "web_search"
    REPORT_GENERATOR = "report_generator"
    GOOGLE_MEETS = "google_meets"
    GOOGLE_OAUTH = "google_oauth"
    JIRA = "jira"
    UML_DIAGRAM_MAKER = "uml_diagram_maker"
    PRESENTATION_MAKER = "presentation_maker"
    IMAGE_GENERATOR = "image_generator"
    KNOWLEDGEBASE_TOOLKIT = "knowledgebase_toolkit"


tool_name_to_cls: dict[ToolName, tuple[Type[ToolMaker], Type[ToolConfig]]] = {
    ToolName.WEB_SEARCH: (WebSearch, WebSearchConfig),
    ToolName.REPORT_GENERATOR: (ReportGenerator, ReportGeneratorConfig),
    ToolName.GOOGLE_MEETS: (MeetsHandler, MeetsConfig),
    ToolName.GOOGLE_OAUTH: (GoogleOauthToolMaker, GoogleOauthConfig),
    ToolName.JIRA: (JiraTools, JiraConfig),
    ToolName.UML_DIAGRAM_MAKER: (AIPlantUMLGenerator, ToolConfig),
    ToolName.PRESENTATION_MAKER: (PresentationToolMaker, PresentationMakerConfig),
    ToolName.IMAGE_GENERATOR: (ImageGenerator, ImageGeneratorConfig),
    ToolName.KNOWLEDGEBASE_TOOLKIT: (RAGToolMaker, RAGToolConfig)
}


def get_all_tools(
    toolnames_to_args: dict[ToolName, dict],
    *,
    platform: Optional[Platform] = None,
    platform_args: Optional[dict] = None,
    platform_helper: Optional[PlatformHelper] = None,
) -> List["BaseTool"]:
    """
    Instantiate and collect AI tools for use in the orchestrator.

    You must supply **either**:
      - `platform` + `platform_args`  (to build a new helper),  
      - OR a `platform_helper` directly.

    :param toolnames_to_args: Mapping of ToolName → kwargs for that tool’s config
    :param platform:  which platform to target (Slack, Jira, etc.)
    :param platform_args:  parameters used to initialize that platform helper
    :param platform_helper:  an already‐constructed helper (skips factory)
    :returns: List of instantiated Tools
    """
    # 1) Resolve or validate the platform helper
    if platform_helper is None:
        if platform is None or platform_args is None:
            raise ValueError(
                "Must provide either (platform + platform_args) or platform_helper"
            )
        platform_helper = platform_helper_factory(platform, platform_args)

    tools: List["BaseTool"] = []

    # 2) Loop through requested tools
    for tool_name, args in toolnames_to_args.items():
        entry = tool_name_to_cls.get(tool_name)
        if not entry:
            # unrecognized tool name → skip
            continue

        tool_cls, tool_config_cls = entry

        # Build OAuth integrations dict for this tool
        oauth_integrations = {
            name: OAUTH_INTEGRATIONS[name]
            for name in tool_cls.REQUESTED_OAUTH_INTEGRATIONS
            if name in OAUTH_INTEGRATIONS
        }

        # Instantiate & collect all AI tools this tool class provides
        instance = tool_cls(
            tool_config=tool_config_cls.model_validate(args),
            oauth_integrations=oauth_integrations,
            platform_helper=platform_helper,
            session=SessionLocal(),
            redis_client=redis.Redis.from_url(f"{os.getenv('REDIS_URL')}/3"),
        )

        tools.extend(instance.create_ai_tools())

    return tools