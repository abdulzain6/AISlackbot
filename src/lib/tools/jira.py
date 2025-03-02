from ...lib.platforms import Platform
from .tool_maker import ToolMaker, ToolConfig
from langchain_core.tools import Tool, tool
from ...database.api_keystore import APIKeyRepository, APIKey


class JiraConfig(ToolConfig):
    user_id: str
    team_id: str
    platform: Platform
    


class JiraTools(ToolMaker):
    def __init__(self, tool_config: JiraConfig):
        ...