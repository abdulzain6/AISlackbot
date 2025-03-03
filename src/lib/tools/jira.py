import logging
from langchain_core.tools import Tool, tool
from typing import Any
from ...lib.integrations.auth.oauth_handler import OAuthClient
from ...lib.platforms.platform_helper import PlatformHelper, TextFormElement
from ...database import DatabaseHelpers
from ...lib.platforms import Platform
from ...database.api_keystore import APIKeyRepository, APIKey
from .tool_maker import ToolMaker, ToolConfig


class JiraConfig(ToolConfig): ...


class JiraTools(ToolMaker):
    REQUESTED_DATABASE_HELPERS = [DatabaseHelpers.API_KEY_REPOSITORY]
    REQUESTED_OAUTH_INTEGRATIONS = []

    def __init__(
        self,
        tool_config: JiraConfig,
        platform_helper: PlatformHelper,
        oauth_integrations: dict[str, OAuthClient],
        database_helpers: dict[DatabaseHelpers, Any],
    ):
        self.api_key_repository: APIKeyRepository = database_helpers[
            DatabaseHelpers.API_KEY_REPOSITORY
        ]
        self.plarform_helper = platform_helper

    def send_api_key_request_form(self):
        try:
            success = self.plarform_helper.send_form_dm(
                "jira_api_key",
                elements=[
                    TextFormElement(
                        type="text",
                        label="Jira Domain",
                        action_id="jira_domain",
                        placeholder="Enter your Jira Domain",
                    ),
                    TextFormElement(
                        type="text",
                        label="Jira API Key",
                        action_id="jira_api_key",
                        placeholder="Enter your Jira API Key",
                    ),
                    TextFormElement(
                        type="text",
                        label="Jira Email",
                        action_id="jira_email",
                        placeholder="Enter your Jira Email",
                    )
                ],
                title=":key: Please provide your Jira API Key. This allows me to interact with your Jira account and do some interesting stuff. :rocket:. Instructions here https://id.atlassian.com/manage-profile/security/api-tokens",
                user_id=self.plarform_helper.owner_uid,
            )
            assert success is True, "Failed to send form DM"
            return "Successfully sent form DM to workplace owner"
        except Exception as e:
            logging.error(f"Failed to send form DM: {e}")
            return f":warning: Failed to send form DM: {e}"

    def create_ai_tools(self) -> list[Tool]:
        @tool
        def ask_owner_for_jira_api_key():
            "Used to request the owner's Jira API Key."
            return self.send_api_key_request_form()

        return [ask_owner_for_jira_api_key]
