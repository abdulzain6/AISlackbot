import redis
from ...lib.platforms.platform_helper import PlatformHelper
from .tool_maker import ToolMaker, ToolConfig
from ..integrations.auth.oauth_handler import OAuthClient
from langchain_core.tools import Tool, tool
from sqlalchemy.orm import Session

class GoogleOauthConfig(ToolConfig):
    ...

class GoogleOauthToolMaker(ToolMaker):
    REQUESTED_OAUTH_INTEGRATIONS = ["google"]

    def __init__(
        self, 
        tool_config: GoogleOauthConfig,
        platform_helper: PlatformHelper,
        oauth_integrations: dict[str, OAuthClient],
        session: Session,        
        redis_client: redis.Redis,
    ):
        self.config = tool_config
        self.oauth_integrations = oauth_integrations
        self.platform_helper = platform_helper

    def create_ai_tools(self) -> list[Tool]:
        @tool
        def create_oauth_link():
            """
            Creates an OAuth link for the user to authenticate with Google.
            Allows you to use other tools taht use google services.
            :return: OAuth link for the user to authenticate with Google.
            """
            link = self.oauth_integrations["google"].get_authorization_url(
                {
                    "team_id": self.platform_helper.team_id,
                    "team_user_id": self.platform_helper.user_id,
                    "app_name": self.platform_helper.platform_name,
                }
            )
            self.platform_helper.send_dm(
                f"Please connect with Google using <{link}|click here>"
            )
            return "Link has been sent to users DM."

        return [create_oauth_link]
