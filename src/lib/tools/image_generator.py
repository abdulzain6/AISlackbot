from langchain_core.tools import tool, Tool
from sqlalchemy.orm import Session
from replicate import Client
from replicate.helpers import FileOutput
from ..integrations.auth.oauth_handler import OAuthClient
from ..platforms.platform_helper import PlatformHelper
from .tool_maker import ToolMaker, ToolConfig

import redis


class ImageGeneratorConfig(ToolConfig):
    replicate_api_key: str


class ImageGenerator(ToolMaker):
    REQUESTED_OAUTH_INTEGRATIONS: list[str] = []

    def __init__(
        self,
        tool_config: ImageGeneratorConfig,
        platform_helper: PlatformHelper,
        oauth_integrations: dict[str, OAuthClient],
        session: Session,
        redis_client: redis.Redis,
    ):
        self.tool_config = tool_config
        self.platform_helper = platform_helper

    def create_ai_tools(self) -> list[Tool]: ...

    def generate_image(
        self, prompt: str, negative_prompt: str, width: int, height: int
    ) -> FileOutput:
        replicate = Client(self.tool_config.replicate_api_key)
        output: FileOutput = replicate.run(
            "bytedance/sdxl-lightning-4step:6f7a773af6fc3e8de9d5a3c00be77c17308914bf67772726aff83496ba1e3bbe",
            input={
                "width": width,
                "height": height,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "num_inference_steps": 4,
            },
            use_file_output=True,
        )
        return output


if __name__ == "__main__":
    out = ImageGenerator(
        tool_config=ImageGeneratorConfig(
            replicate_api_key=""
        ),
        platform_helper=None,
        oauth_integrations={},
        session=None,
        redis_client=None,
    ).generate_image(
        prompt="A cat",
        negative_prompt="",
        width=1024,
        height=1024,
    )
    print(out)
