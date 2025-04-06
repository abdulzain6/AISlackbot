from abc import ABC, abstractmethod
from langchain_core.tools import Tool
from pydantic import BaseModel
import redis
from sqlalchemy.orm import Session
from ...lib.integrations.auth.oauth_handler import OAuthClient
from ...lib.platforms.platform_helper import PlatformHelper


class ToolConfig(BaseModel):
    ...


class ToolMaker(ABC):
    REQUESTED_OAUTH_INTEGRATIONS: list[str] = []

    @abstractmethod
    def __init__(
        self, 
        tool_config: ToolConfig,
        platform_helper: PlatformHelper,
        oauth_integrations: dict[str, OAuthClient],
        session: Session,
        redis_client: redis.Redis,
    ):
        ...

    @abstractmethod
    def create_ai_tools(self) -> list[Tool]:
        ...