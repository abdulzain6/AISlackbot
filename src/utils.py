from slack_bolt import App
from slack_sdk.web import WebClient
from slack_sdk.errors import SlackApiError
from typing import List, Optional
import logging


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