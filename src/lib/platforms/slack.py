import re
import logging
import json
from slack_sdk.web import WebClient
from slack_sdk.errors import SlackApiError
from typing import Any, Dict, List, Optional
from typing import Optional
from .platform_helper import PlatformHelper, FormElement



class SlackHelper(PlatformHelper):
    platform_name = "slack"

    def __init__(self, client: WebClient, user_id: str = None):
        """
        Initialize SlackHelper with a Slack WebClient and optionally a user ID.
        Automatically retrieves and stores the team ID upon initialization.
        """
        self.client = client
        self._user_id = user_id

    @property
    def owner_uid(self) -> Optional[str]:
        """
        Retrieves the workspace owner's user ID via the Slack API.
        It calls users.list and searches for the primary owner.
        Returns None if no owner is found or the API call fails.
        """
        response: dict = self.client.users_list()
        if response.get("ok"):
            members: List[Dict] = response.get("members", [])
            for member in members:
                if member.get("is_primary_owner"):
                    owner_id: Optional[str] = member.get("id")
                    logging.info(f"Found primary owner with ID: {owner_id}")
                    return owner_id
            logging.error("No primary owner found in the users list")
            return None
        logging.error(f"Failed to retrieve users list: {response.get('error')}")
        return None
    
    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def team_id(self) -> str:
        return self._get_team_id()

    def _get_team_id(self) -> Optional[str]:
        """
        Retrieve the team ID using the auth.test endpoint.
        Returns None if the request fails.
        """
        response = self.client.auth_test()
        if response["ok"]:
            team_id = response.get("team_id")
            logging.info(f"Successfully retrieved team ID: {team_id}")
            return team_id
        else:
            logging.error(f"Failed to get team ID: {response.get('error')}")
            return None

    def convert_to_slack_markdown(self, text: str) -> str:
        """Convert Markdown links to Slack's format"""
        return re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f"<{m.group(2)}|{m.group(1)}>", text
        )

    def to_block(self, message: str) -> list[dict[str, str]]:
        """Convert a message to a Slack block kit format"""
        converted_message = self.convert_to_slack_markdown(message.strip())
        return [
            {"type": "section", "text": {"type": "mrkdwn", "text": converted_message}},
            {"type": "divider"},
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": ":sparkles: *Powered by SlackBotAI*"}
                ],
            },
        ]

    def send_message(self, channel_id: str, message: str, thread_ts: str = None):
        """Send a message to a Slack channel with optional threading support"""
        try:
            self.client.chat_postMessage(
                channel=channel_id, blocks=self.to_block(message), thread_ts=thread_ts
            )
            logging.info(f"Message successfully sent to channel {channel_id}")
        except SlackApiError as e:
            logging.error(
                f"Error sending message to channel {channel_id}: {e.response['error']}"
            )

    def send_dm(self, message: str):
        """Send a direct message to a Slack user"""
        target_user = self.user_id
        if not target_user:
            logging.error("No user ID provided for sending DM")
            return

        try:
            response = self.client.conversations_open(users=[target_user])
            if response["ok"]:
                channel_id = response["channel"]["id"]
                self.client.chat_postMessage(
                    channel=channel_id, blocks=self.to_block(message)
                )
                logging.info(f"Direct message successfully sent to user {target_user}")
            else:
                logging.error(
                    f"Failed to open conversation with user {target_user}: {response['error']}"
                )
        except SlackApiError as e:
            logging.error(
                f"Error sending DM to user {target_user}: {e.response['error']}"
            )

    def get_chat_history(
        self, channel_id: str, limit: int = 10, thread_ts: str = None
    ) -> Optional[List[Dict[str, str]]]:
        """Get chat history from Slack with optimized user/bot info retrieval"""
        logging.info(f"Fetching chat history for channel {channel_id}")

        try:
            # Get messages based on whether it's a thread or regular channel history
            if thread_ts:
                response = self.client.conversations_replies(
                    channel=channel_id, ts=thread_ts, limit=limit
                )
            else:
                response = self.client.conversations_history(
                    channel=channel_id, limit=limit
                )

            messages = response.get("messages", [])
            if not messages:
                return []
            
            # Extract all unique user and bot IDs in a single pass
            user_ids = set()
            bot_ids = set()

            for message in messages:
                if "user" in message:
                    user_ids.add(message["user"])
                elif "bot_id" in message:
                    bot_ids.add(message["bot_id"])

            # Batch fetch user info
            user_cache = {}
            if user_ids:
                for user_id in user_ids:
                    try:
                        user_info = self.client.users_info(user=user_id).get("user", {})
                        user_cache[user_id] = user_info
                    except Exception as e:
                        logging.error(f"Error fetching user {user_id}: {str(e)}")
                        user_cache[user_id] = {}

            # Batch fetch bot info
            bot_cache = {}
            if bot_ids:
                for bot_id in bot_ids:
                    try:
                        bot_info = self.client.bots_info(bot=bot_id).get("bot", {})
                        bot_cache[bot_id] = bot_info
                    except Exception as e:
                        logging.error(f"Error fetching bot {bot_id}: {str(e)}")
                        bot_cache[bot_id] = {}

            # Process messages with the cached user/bot info
            results = []
            for message in messages:
                if "user" in message:
                    user_id = message["user"]
                    user_info = user_cache.get(user_id, {})
                    profile = user_info.get("profile", {})
                    display_name = (
                        profile.get("display_name")
                        or profile.get("real_name")
                        or user_info.get("name", "Unknown")
                    )
                elif "bot_id" in message:
                    bot_id = message["bot_id"]
                    bot_info = bot_cache.get(bot_id, {})
                    display_name = bot_info.get("name", "Unknown Bot")
                else:
                    display_name = "Unknown"

                results.append(
                    {"display_name": display_name, "message": message.get("text", "")}
                )

            # Return results in appropriate order based on context
            if not thread_ts:
                results.reverse()  # Only reverse for regular channel history

            logging.info(
                f"Successfully retrieved {len(results)} messages with display names"
            )
            return results

        except Exception as e:
            logging.error(
                f"Error retrieving chat history for channel {channel_id}: {str(e)}"
            )
            return None

    def send_form_dm(
        self,
        action_id: str,
        elements: list[FormElement],
        title: str = "Please complete this form",
        metadata: dict = None,
        user_id: str = None,
        extra_context: str = ""
    ) -> bool:
        """
        Send a form to a user via DM and return success status
        """
        target_user = user_id if user_id else self.user_id

        if not target_user:
            logging.error("No user ID provided for sending form")
            return False

        try:
            # Open DM channel with user
            response = self.client.conversations_open(users=[target_user])
            if not response["ok"]:
                logging.error(
                    f"Failed to open conversation with user {target_user}: {response['error']}"
                )
                return False

            channel_id = response["channel"]["id"]

            # Build form blocks
            form_blocks = []

            # Add header
            form_blocks.append(
                {"type": "header", "text": {"type": "plain_text", "text": title}}
            )

            # Add divider
            form_blocks.append({"type": "divider"})

            # Process each form element
            for idx, element in enumerate(elements):
                if element.type == "text":
                    element_block = {
                        "type": "input",
                        "block_id": f"block_{idx}",
                        "label": {"type": "plain_text", "text": element.label},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": element.action_id,
                            "multiline": element.multiline,
                        },
                    }

                    # Add optional properties if provided
                    if element.placeholder:
                        element_block["element"]["placeholder"] = {
                            "type": "plain_text",
                            "text": element.placeholder,
                        }
                    if element.initial_value is not None:
                        element_block["element"][
                            "initial_value"
                        ] = element.initial_value
                    if element.max_length is not None:
                        element_block["element"]["max_length"] = element.max_length

                    form_blocks.append(element_block)

            # Add submit button
            form_blocks.append(
                {
                    "type": "actions",
                    "block_id": "form_submit",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Submit"},
                            "style": "primary",
                            "value": json.dumps(
                                {"action_id": action_id, "metadata": metadata or {}}
                            ),
                            "action_id": f"{action_id}_submit",
                        }
                    ],
                }
            )

            # Add footer
            form_blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f":pencil: *Please complete this form* {extra_context}",
                        }
                    ],
                }
            )

            logging.info(f"Blocks sending: {form_blocks}")
            # Send the message with form blocks
            self.client.chat_postMessage(channel=channel_id, blocks=form_blocks)
            logging.info(
                f"Form successfully sent to user {target_user} with action_id {action_id}"
            )
            return True

        except SlackApiError as e:
            logging.error(
                f"Error sending form to user {target_user}: {e.response['error']}"
            )
            return False

    @classmethod
    def from_token(cls, token: str, user_id: str) -> "SlackHelper":
        return SlackHelper(WebClient(token=token), user_id)
