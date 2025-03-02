from enum import Enum
from .platform_helper import PlatformHelper
from .slack import SlackHelper

class Platform(Enum):
    SLACK = "SLACK"


def platform_helper_factory(platform: Platform, args: dict) -> PlatformHelper:
    if platform == Platform.SLACK:
        return SlackHelper.from_token(args["slack_token"], args["user_id"])
    else:
        raise ValueError(f"Unsupported platform: {platform}")