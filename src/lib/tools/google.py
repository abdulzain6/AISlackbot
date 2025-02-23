from typing import Callable
from ...lib.platforms import Platform, send_dm
from .tool_maker import ToolMaker, ToolConfig
from langchain_core.tools import Tool, tool
from ..integrations.auth.oauth_handler import OAuthClient
from ...globals import OAUTH_INTEGRATIONS


class GoogleOauthConfig(ToolConfig):
    send_dm_callable: Callable[[Platform, str, str], None] = send_dm
    platform: Platform = Platform.SLACK
    user_id: str
    team_id: str
    oauth_client: OAuthClient = OAUTH_INTEGRATIONS["google"]

    class Config:
        arbitrary_types_allowed = True


class GoogleOauthToolMaker(ToolMaker):
    def __init__(self, tool_config: GoogleOauthConfig):
        self.config = tool_config

    def create_ai_tools(self) -> list[Tool]:

        @tool
        def create_oauth_link():
            """
            Creates an OAuth link for the user to authenticate with Google.
            :return: OAuth link for the user to authenticate with Google.
            """
            link = self.config.oauth_client.get_authorization_url(
                {
                    "team_id": self.config.team_id,
                    "team_user_id": self.config.user_id,
                    "app_name": self.config.platform.value.lower(),
                }
            )
            self.config.send_dm_callable(
                self.config.platform,
                f"Please connect with Google using <{link}|click here>",
                self.config.user_id,
            )
            return "Link has been sent to users DM."

        return [create_oauth_link]
