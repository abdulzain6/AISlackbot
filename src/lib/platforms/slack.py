import re
import logging
from slack_sdk.web import WebClient
from slack_sdk.errors import SlackApiError
from typing import Any, Dict, List, Optional, TypedDict
from ...globals import client


class SendMessageConfig(TypedDict):
    channel_id: str
    thread_ts: Optional[str]


def convert_to_slack_markdown(text: str) -> str:
    """Convert Markdown links to Slack's format"""
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', lambda m: f"<{m.group(2)}|{m.group(1)}>", text)


def to_block(message: str) -> list[dict[str, str]]:
    """Convert a message to a Slack block kit format"""
    converted_message = convert_to_slack_markdown(message.strip())
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": converted_message}},
        {"type": "divider"},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": ":sparkles: *Powered by SlackBotAI*"}]},
    ]


def send_message_to_slack(channel_id: str, message: str, thread_ts: str = None):
    """Send a message to a Slack channel with optional threading support"""
    try:
        client.chat_postMessage(
            channel=channel_id, blocks=to_block(message), thread_ts=thread_ts
        )
        logging.info(f"Message successfully sent to channel {channel_id}")
    except SlackApiError as e:
        logging.error(f"Error sending message to channel {channel_id}: {e.response['error']}")


def send_dm_to_slack(user_id: str, message: str):
    """Send a direct message to a Slack user"""
    try:
        response = client.conversations_open(users=[user_id])
        if response['ok']:
            channel_id = response['channel']['id']
            client.chat_postMessage(
                channel=channel_id, blocks=to_block(message)
            )
            logging.info(f"Direct message successfully sent to user {user_id}")
        else:
            logging.error(f"Failed to open conversation with user {user_id}: {response['error']}")
    except SlackApiError as e:
        logging.error(f"Error sending DM to user {user_id}: {e.response['error']}")


def get_chat_history(client: WebClient, channel_id: str, limit: int = 10, thread_ts: str = None) -> Optional[List[Dict[str, str]]]:
    logging.info(f"Fetching chat history for channel {channel_id}")

    if thread_ts:
        response = client.conversations_replies(channel=channel_id, ts=thread_ts, limit=limit)
        initial_message = response.get('messages', [])[0] if response.get('messages') else {}
        is_thread_on_bot_message = 'bot_id' in initial_message
        logging.info(f"Thread {'is' if is_thread_on_bot_message else 'is not'} on a bot's message")

    else:
        response = client.conversations_history(channel=channel_id, limit=limit)

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
                    user_info = client.users_info(user=user_id).get("user", {})
                    user_cache[user_id] = user_info
                except Exception as e:
                    logging.error(f"Error fetching user {user_id}: {e}")
                    user_cache[user_id] = {}
            user_info = user_cache[user_id]
            display_name = (user_info.get("profile", {}).get("display_name") or
                            user_info.get("profile", {}).get("real_name") or
                            user_info.get("name", "Unknown"))
        elif "bot_id" in message:
            bot_id = message["bot_id"]
            if bot_id not in bot_cache:
                try:
                    bot_info = client.bots_info(bot=bot_id).get("bot", {})
                    bot_cache[bot_id] = bot_info
                except Exception as e:
                    logging.error(f"Error fetching bot {bot_id}: {e}")
                    bot_cache[bot_id] = {}
            bot_info = bot_cache[bot_id]
            display_name = bot_info.get("name", "Unknown Bot")
        results.append({
            "display_name": display_name,
            "message": message.get("text", "")
        })

    logging.info(f"Successfully retrieved {len(results)} messages with display names")
    return list(reversed(results)) if not thread_ts else results