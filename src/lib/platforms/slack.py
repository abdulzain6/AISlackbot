import re
import logging
import json
from slack_sdk.web import WebClient
from slack_sdk.errors import SlackApiError
from typing import Any, Dict, List, Optional
from typing import Optional
from .platform_helper import PlatformHelper, FormElement


class SlackHelper(PlatformHelper):
    platform_name = "SLACK"

    def __init__(self, client: WebClient, user_id: str = None):
        """
        Initialize SlackHelper with a Slack WebClient and optionally a user ID.
        Automatically retrieves and stores the team ID upon initialization.
        """
        self.client = client
        self._user_id = user_id

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

    def send_message(
        self, channel_id: str, message: str, thread_ts: str = None
    ):
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
        logging.info(f"Fetching chat history for channel {channel_id}")

        if thread_ts:
            response = self.client.conversations_replies(
                channel=channel_id, ts=thread_ts, limit=limit
            )
            initial_message = (
                response.get("messages", [])[0] if response.get("messages") else {}
            )
            is_thread_on_bot_message = "bot_id" in initial_message
            logging.info(
                f"Thread {'is' if is_thread_on_bot_message else 'is not'} on a bot's message"
            )

        else:
            response = self.client.conversations_history(
                channel=channel_id, limit=limit
            )

        messages = response.get("messages", [])
        user_cache: Dict[str, Dict[str, Any]] = {}
        bot_cache: Dict[str, Dict[str, Any]] = {}
        results: List[Dict[str, str]] = []

        for message in messages:
            display_name = "Unknown"
            if "user" in message:
                user_id = message["user"]
                if user_id not in user_cache:
                    try:
                        user_info = self.client.users_info(user=user_id).get("user", {})
                        user_cache[user_id] = user_info
                    except Exception as e:
                        logging.error(f"Error fetching user {user_id}: {e}")
                        user_cache[user_id] = {}
                user_info = user_cache[user_id]
                display_name = (
                    user_info.get("profile", {}).get("display_name")
                    or user_info.get("profile", {}).get("real_name")
                    or user_info.get("name", "Unknown")
                )
            elif "bot_id" in message:
                bot_id = message["bot_id"]
                if bot_id not in bot_cache:
                    try:
                        bot_info = self.client.bots_info(bot=bot_id).get("bot", {})
                        bot_cache[bot_id] = bot_info
                    except Exception as e:
                        logging.error(f"Error fetching bot {bot_id}: {e}")
                        bot_cache[bot_id] = {}
                bot_info = bot_cache[bot_id]
                display_name = bot_info.get("name", "Unknown Bot")

            results.append(
                {"display_name": display_name, "message": message.get("text", "")}
            )

        logging.info(
            f"Successfully retrieved {len(results)} messages with display names"
        )
        return list(reversed(results)) if not thread_ts else results

    def send_form_dm(
        self,
        action_id: str,
        elements: list[FormElement],
        title: str = "Please complete this form",
        metadata: dict = None,
        user_id: str = None,
    ) -> bool:
        """
        Send a form to a user via DM and return success status
        """
        target_user = user_id or self.user_id
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
                            "text": ":pencil: *Please complete this form*",
                        }
                    ],
                }
            )

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
    def from_token(cls, token: str, user_id: str) -> 'SlackHelper':
        return cls(WebClient(token=token), user_id)