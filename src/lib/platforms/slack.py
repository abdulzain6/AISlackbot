import re
import logging
from slack_sdk.web import WebClient
from slack_sdk.errors import SlackApiError
from typing import List, Optional, TypedDict
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
    client.chat_postMessage(
        channel=channel_id, blocks=to_block(message)
    )


def get_chat_history(client: WebClient, channel_id: str, limit: int = 10) -> Optional[List[dict]]:
    """Retrieve the chat history for a specified channel with error handling"""
    logging.info(f"Fetching chat history for channel {channel_id}")
    try:
        response = client.conversations_history(
            channel=channel_id,
            limit=limit
        )
        messages: List[dict] = response["messages"]
        logging.info(f"Successfully retrieved {len(messages)} messages from history")
        return messages
    
    except SlackApiError as e:
        logging.error(f"Error fetching chat history: {e.response['error']}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error in get_chat_history: {str(e)}", exc_info=True)
        return None