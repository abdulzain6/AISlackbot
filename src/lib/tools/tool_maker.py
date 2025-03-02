from abc import ABC, abstractmethod
from typing import Any
from langchain_core.tools import Tool
from pydantic import BaseModel
from ...database import DatabaseHelpers
from ...lib.integrations.auth.oauth_handler import OAuthClient
from ...lib.platforms.platform_helper import PlatformHelper


class ToolConfig(BaseModel):
    ...


class ToolMaker(ABC):
    REQUESTED_OAUTH_INTEGRATIONS: list[str] = []
    REQUESTED_DATABASE_HELPERS: list[DatabaseHelpers] = []

    @abstractmethod
    def __init__(
        self, 
        tool_config: ToolConfig,
        platform_helper: PlatformHelper,
        oauth_integrations: dict[str, OAuthClient],
        database_helpers: dict[DatabaseHelpers, Any],
    ):
        ...

    @abstractmethod
    def create_ai_tools(self) -> list[Tool]:
        ...