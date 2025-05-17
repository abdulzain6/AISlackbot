from langchain_core.tools import BaseTool
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
    DESCRIPTION = """The ToolMaker allows the creation of AI-generated images based on user-defined prompts and specifications."""

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

    def create_ai_tools(self) -> list[BaseTool]:
        def generate_image(prompt: str, negative_prompt: str, width: int, height: int):
            """Used to generate an image and send it to the user."""
            file = self.generate_image(prompt, negative_prompt, width, height)
            self.platform_helper.send_file(
                file.read(), "image.png"
            )
            return "Image generated and sent to the user. Ask him to check chat for file."
        return [generate_image]

    def generate_image(
        self, prompt: str, negative_prompt: str, width: int, height: int
    ) -> FileOutput:
        # Ensure the width and height are divisible by 8, adjust to the nearest value if necessary
        adjusted_width = (width // 8) * 8
        adjusted_height = (height // 8) * 8

        if adjusted_width != width or adjusted_height != height:
            print(
                f"Adjusting dimensions: Width changed from {width} to {adjusted_width}, "
                f"Height changed from {height} to {adjusted_height} to meet divisibility requirements."
            )

        replicate = Client(self.tool_config.replicate_api_key)
        output: FileOutput = replicate.run(
            "bytedance/sdxl-lightning-4step:6f7a773af6fc3e8de9d5a3c00be77c17308914bf67772726aff83496ba1e3bbe",
            input={
                "width": adjusted_width,
                "height": adjusted_height,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "num_inference_steps": 4,
            },
            use_file_output=True,
        )[0]
        return output


if __name__ == "__main__":
    out = ImageGenerator(
        tool_config=ImageGeneratorConfig(replicate_api_key=""),
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
