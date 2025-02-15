from enum import Enum
from .slack import send_message_to_slack, SendMessageConfig as SendMessageConfigSlack

class Platform(Enum):
    SLACK = "SLACK"

PLATFORM_TO_CONFIG = {
    Platform.SLACK: SendMessageConfigSlack,
}

SendMessageConfig = SendMessageConfigSlack

def send_message(platform: Platform, config: SendMessageConfig, message: str):
    validate_config(config, platform)
    if platform == Platform.SLACK:
        send_message_to_slack(**config, message=message)
    else:
        raise ValueError(f"Unsupported platform: {platform}")

def validate_config(config: SendMessageConfig, platform: Platform):
    if platform == Platform.SLACK:
        required_keys = SendMessageConfigSlack.__annotations__.keys()
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Missing required key: {key}")
            if not isinstance(config[key], SendMessageConfigSlack.__annotations__[key]):
                raise TypeError(f"Key {key} is expected to be of type {SendMessageConfigSlack.__annotations__[key]}")
    else:
        raise ValueError(f"Unsupported platform: {platform}")