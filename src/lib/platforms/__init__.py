from enum import Enum
from .slack import send_message_to_slack, SendMessageConfig, send_dm_to_slack

class Platform(Enum):
    SLACK = "SLACK"


def send_message(platform: Platform, config: SendMessageConfig, message: str):
    if platform == Platform.SLACK:
        send_message_to_slack(**config, message=message)
    else:
        raise ValueError(f"Unsupported platform: {platform}")

def send_dm(platform: Platform, message: str, user_id: str):
    if platform == Platform.SLACK:
        send_dm_to_slack(message=message, user_id=user_id)
    else:
        raise ValueError(f"Unsupported platform: {platform}")