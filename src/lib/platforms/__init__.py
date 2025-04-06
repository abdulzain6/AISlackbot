from enum import Enum

import redis

from ...globals import REDIS_URL
from .platform_helper import PlatformHelper
from .slack import SlackHelper

class Platform(Enum):
    SLACK = "SLACK"


def platform_helper_factory(platform: Platform, args: dict) -> PlatformHelper:
    if platform == Platform.SLACK:
        return SlackHelper.from_token(args["slack_token"], args["user_id"], redis=redis.Redis.from_url(REDIS_URL), init_auth=False)
    else:
        raise ValueError(f"Unsupported platform: {platform}")