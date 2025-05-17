from datetime import datetime
from io import IOBase
import re
import logging
import json
from redis import Redis
import redis
import requests
from slack_sdk.web import WebClient
from slack_sdk.errors import SlackApiError
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from typing import Any, Dict, List, Optional, Tuple, Union
from typing import Optional
from .platform_helper import PlatformHelper, FormElement
from markdown2slack.app import Convert


class SlackHelper(PlatformHelper):
    platform_name = "slack"

    def __init__(
        self,
        client: WebClient,
        redis: Redis,
        user_id: str | None = None,
        init_auth: bool = True,
        channel_id: str | None = None,
        thread_ts: str | None = None,
        message_ts: str | None = None,
    ):
        """
        Initialize SlackHelper with a Slack WebClient and optionally a user ID.
        Automatically retrieves and stores the team ID upon initialization.
        """
        self.client = client
        self.redis = redis
        self._user_id = user_id
        self.thread_ts = thread_ts
        self.message_ts = message_ts
        self.channel_id = channel_id

        if init_auth:
            auth_info = self._get_auth_info()
            self.bot_id = auth_info.get("bot_id")
            self._team_id = auth_info.get("team_id")
            logging.info(
                f"TeamID: {self.team_id} BotID: {self.bot_id} Auth Test: {auth_info}"
            )
        else:
            self.bot_id = None
            self._team_id = None

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
        if not self._team_id:
            auth_info = self._get_auth_info()
            self.bot_id = auth_info.get("bot_id")
            self._team_id = auth_info.get("team_id")

        return self._team_id

    def get_recent_file_info(
        self, channel_id: str | None = None, limit: int = 2
    ) -> List[dict]:
        """
        Fetches the last `limit` messages from a channel and threads, and returns a list of file information.
        Ensures filenames are unique by keeping only the latest file based on timestamp.

        Args:
            channel_id (str): ID of the Slack channel.
            limit (int): Number of recent messages to scan. Default is 2.

        Returns:
            List[dict]: List of dictionaries containing file information. Each dictionary includes:
                - name (str): The file name.
                - id (str): The file ID.
                - is_latest (bool): True if this is the latest file, False otherwise.
                - message (str): "This is the latest file" for the latest, else an empty string.
        """
        file_info_dict = {}  # To store unique files with the latest timestamp
        try:
            # Fetch recent messages from the channel
            response = self.client.conversations_history(
                channel=channel_id if channel_id else self.channel_id,
                limit=limit,
            )
            messages = response.get("messages", [])

            for msg in messages:
                # Check for files in the main message
                if "files" in msg:
                    for file in msg["files"]:
                        timestamp = float(msg["ts"])
                        file_name = file["name"]
                        file_id = file["id"]

                        # Update if the file_name is new or if there's a newer timestamp
                        if file_name not in file_info_dict or timestamp > file_info_dict[file_name]["timestamp"]:
                            file_info_dict[file_name] = {
                                "name": file_name,
                                "id": file_id,
                                "timestamp": timestamp,
                            }
                # Check if the message starts a thread using `thread_ts`
                if "thread_ts" in msg:
                    thread_ts = msg["thread_ts"]

                    # Fetch replies in the thread
                    thread_replies = self.client.conversations_replies(
                        channel=channel_id if channel_id else self.channel_id,
                        ts=thread_ts,
                    ).get("messages", [])

                    for reply in thread_replies:
                        if "files" in reply:
                            for file in reply["files"]:
                                timestamp = float(reply["ts"])
                                file_name = file["name"]
                                file_id = file["id"]

                                # Update if the file_name is new or if there's a newer timestamp
                                if file_name not in file_info_dict or timestamp > file_info_dict[file_name]["timestamp"]:
                                    file_info_dict[file_name] = {
                                        "name": file_name,
                                        "id": file_id,
                                        "timestamp": timestamp,
                                    }

        except Exception as e:
            print(f"Error fetching files: {e}")

        # Process the dictionary to add additional keys and return the final list
        if file_info_dict:
            latest_file_name = max(file_info_dict.values(), key=lambda x: x["timestamp"])["name"]

        file_info_list = []
        for file_details in file_info_dict.values():
            is_latest = file_details["name"] == latest_file_name
            file_info_list.append({
                "name": file_details["name"],
                "id": file_details["id"],
                "is_latest": is_latest,
                "message": "This is the latest file" if is_latest else "",
            })

        return file_info_list
    
    def get_file_bytes(self, file_id: str) -> bytes:
        """
        Retrieve the raw bytes of a file from Slack using its file ID.
        Only supports text-based formats (e.g., .md, .json, .txt).
        Raises an error if the file is not text-based or if it exceeds 20,000 bytes.
        """
        file_info = self._get_file_info(file_id)
        file_name = file_info["name"]
        file_size = file_info.get("size", 0)

        max_size_bytes = 30 * 1024 * 1024  # 30 MB in bytes
        if file_size > max_size_bytes:
            raise ValueError(f"File {file_name} too large ({file_size} bytes)")

        # Download the raw file
        download_url = file_info.get("url_private_download") or file_info["url_private"]
        headers = {"Authorization": f"Bearer {self.client.token}"}
        r = requests.get(download_url, headers=headers)
        if r.status_code != 200:
            raise ValueError(
                f"Failed to download file content: HTTP {r.status_code}"
            )

        return r.content

    def read_file(self, file_id: str) -> str:
        """
        Read the content of a file from Slack using its file ID.
        Only supports text-based formats (e.g., .md, .json, .txt).
        Raises an error if the file is not text-based or if it exceeds 20,000 characters.
        """
        # Get the file bytes
        file_bytes = self.get_file_bytes(file_id)

        # Decode & final length check
        try:
            text = file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            raise ValueError(f"Could not decode file as UTF‑8")

        if len(text) > 20_000:
            raise ValueError(f"File content exceeds 20,000 characters")

        return text

    def get_file_name(self, file_id: str) -> str:
        """
        Retrieve the name of a file from Slack using its file ID.
        """
        file_info = self._get_file_info(file_id)
        return file_info["name"]

    def _get_file_info(self, file_id: str) -> dict:
        """
        Helper method to fetch file metadata from Slack using its file ID.
        """
        resp = self.client.files_info(file=file_id)
        if not resp["ok"]:
            raise ValueError(f"Failed to fetch file info: {resp['error']}")
        return resp["file"]

    def _get_auth_info(self) -> Optional[str]:
        """
        Retrieve the team ID using the auth.test endpoint.
        Returns None if the request fails.
        """
        response = self.client.auth_test()
        if response["ok"]:
            return response
        else:
            raise ValueError(f"Failed to get auth info: {response['error']}")

    def convert_to_slack_markdown(self, text: str) -> str:
        """Convert Markdown links to Slack's format"""
        converter = Convert()
        return converter.markdown_to_slack_format(text)

    def to_block(self, message: str) -> List[Dict[str, Any]]:
        """
        Convert a message to a Slack block kit format.
        Removes asterisks if they are not rendering correctly for emphasis.
        """
        # Removing `**` used for bold if Slack Markdown doesn't handle it well
        text_without_asterisks = message.replace("**", "")

        # If further formatting is needed, it can be added here. For now, just remove the bold.
        converted_message = self.convert_to_slack_markdown(
            text_without_asterisks.strip()
        )

        return [
            {"type": "section", "text": {"type": "mrkdwn", "text": converted_message}},
        ]

    def send_message(self, message: str, channel_id: str | None = None, thread_ts: str = None):
        """Send a message to a Slack channel with optional threading support"""
        try:
            self.client.chat_postMessage(
                channel=channel_id if channel_id else self.channel_id,
                blocks=self.to_block(message),
                thread_ts=thread_ts or self.thread_ts,
            )
            logging.info(f"Message successfully sent to channel {channel_id}")
        except SlackApiError as e:
            logging.error(
                f"Error sending message to channel {channel_id}: {e.response['error']}"
            )

    def send_picture(
        self,
        image_url: str,
        alt_text: str,
        channel_id: str | None = None,
        thread_ts: str | None = None,
    ):
        """Send a picture to a Slack channel with optional threading support"""
        try:
            # Build a Slack block with an image
            image_block = [
                {
                    "type": "image",
                    "image_url": image_url,
                    "alt_text": alt_text,
                }
            ]

            # Send the image as a message with the block
            self.client.chat_postMessage(
                channel=channel_id if channel_id else self.channel_id,
                blocks=image_block,
                thread_ts=thread_ts or self.thread_ts,
            )
            logging.info(
                f"Picture successfully sent to channel {channel_id} with URL {image_url}"
            )
        except SlackApiError as e:
            logging.error(
                f"Error sending picture to channel {channel_id}: {e.response['error']}"
            )

    def send_file(
        self,
        file: Optional[Union[str, bytes, IOBase]] = None,
        title: Optional[str] = None,
        channel_id: Optional[str] = None,
        thread_ts: Optional[str] = None,
        alt_txt: Optional[str] = None,
        initial_comment: Optional[str] = None,
        request_file_info: bool = True,
        **kwargs,
    ):
        """
        Send a picture file to a Slack channel and display a preview using the files_upload_v2 method.

        Parameters:
            file (str, bytes, IOBase): The file to upload. Can be a file path, raw bytes, or file-like object.
            title (str): Title of the file shown in Slack.
            channel_id (str): The Slack channel ID. Defaults to `self.channel_id` if not provided.
            thread_ts (str): Thread timestamp to send the file in a thread. Defaults to `self.thread_ts` if not provided.
            alt_txt (str): Alternative text for the image display.
            initial_comment (str): Initial comment to accompany the uploaded file.
            request_file_info (bool): Whether to request file info. Kept for compatibility as it is now optional.
            kwargs: Additional parameters for the files_upload API method.
        """
        try:
            # Upload the file using the Slack SDK's files_upload_v2 method
            response = self.client.files_upload_v2(
                file=file,
                filename=title,  # Maps the title to filename for better display
                title=title,  # Title displayed in Slack
                channel=channel_id or self.channel_id,
                thread_ts=thread_ts or self.thread_ts,
                initial_comment=initial_comment,
                request_file_info=request_file_info,
                alt_txt=alt_txt,
                **kwargs,
            )

            # Log the details of the uploaded file for debugging purposes
            file_id = response.get("file", {}).get("id")
            if file_id:
                logging.info(
                    f"File successfully uploaded to channel {channel_id or self.channel_id} "
                    f"with file ID {file_id} and title '{title}'"
                )
            else:
                logging.warning(
                    "File uploaded but no file ID was retrieved from the response."
                )

        except SlackApiError as e:
            # Handle Slack API errors gracefully
            logging.error(
                f"Error uploading file to channel {channel_id or self.channel_id}: {e.response['error']}"
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
    ) -> Optional[List[BaseMessage]]:
        """Get chat history from Slack with optimized caching and user/bot info retrieval"""
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

            # Initialize caches
            user_cache = {}
            bot_cache = {}
            results = []

            # Helper function to get cached info or fetch & cache if not present
            def fetch_and_cache_info(cache_key: str, fetch_func) -> dict:
                cached_data = self.redis.get(cache_key)
                if cached_data:
                    return json.loads(cached_data)
                try:
                    data = fetch_func()
                    self.redis.set(cache_key, json.dumps(data))
                    return data
                except Exception as e:
                    logging.error(f"Error fetching info for {cache_key}: {e}")
                    return {}

            for message in messages:
                content = message.get("text", "")
                cache_key = None
                if "user" in message and "bot_id" not in message:
                    user_id = message["user"]
                    if user_id not in user_cache:
                        cache_key = f"slack:{self.team_id}:{user_id}"
                        user_cache[user_id] = fetch_and_cache_info(
                            cache_key,
                            lambda: self.client.users_info(user=user_id).get(
                                "user", {}
                            ),
                        )
                    user_info = user_cache.get(user_id, {})
                    profile = user_info.get("profile", {})
                    display_name = (
                        profile.get("display_name")
                        or profile.get("real_name")
                        or user_info.get("name", "Unknown")
                    )
                    results.append(HumanMessage(content=f"{display_name}: {content}"))

                elif "bot_id" in message:
                    logging.info(f"Bot message: {message}, {self.bot_id}")
                    bot_id = message["bot_id"]
                    if bot_id not in bot_cache and bot_id != self.bot_id:
                        cache_key = f"slack:{self.team_id}:bot:{bot_id}"
                        bot_cache[bot_id] = fetch_and_cache_info(
                            cache_key,
                            lambda: self.client.bots_info(bot=bot_id).get("bot", {}),
                        )
                    if bot_id == self.bot_id:
                        results.append(AIMessage(content=content))
                    else:
                        results.append(HumanMessage(content=f"Unknown: {content}"))

                else:
                    results.append(HumanMessage(content=f"Unknown: {content}"))

            # Reverse order for regular channel history (not thread replies)
            if not thread_ts:
                results.reverse()

            logging.info(
                f"Successfully retrieved {len(results)} messages as Langchain objects"
            )
            return results

        except Exception as e:
            import traceback

            traceback.print_exc()
            logging.error(
                f"Error retrieving chat history for channel {channel_id}: {e}"
            )
            return None

    def send_form_dm(
        self,
        action_id: str,
        elements: list[FormElement],
        title: str = "Please complete this form",
        metadata: dict = None,
        user_id: str | None = None,
        extra_context: str = "",
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
    def from_token(
        cls,
        token: str,
        user_id: str,
        redis: redis.Redis,
        init_auth: bool = True,
        **kwargs,
    ) -> "SlackHelper":
        return SlackHelper(
            WebClient(token=token),
            redis=redis,
            user_id=user_id,
            init_auth=init_auth,
            **kwargs,
        )
