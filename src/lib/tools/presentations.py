from langchain_core.tools import BaseTool, tool
from sqlalchemy.orm import Session
from ...lib.integrations.auth.oauth_handler import OAuthClient
from ...lib.platforms.platform_helper import PlatformHelper
from .presentation_maker.presentation_maker import PresentationMaker, PresentationInput
from .presentation_maker.models import make_template_db_manager
from .tool_maker import ToolMaker, ToolConfig
from ..models.llm import LLMConfig
from .image_generator import ImageGenerator, ImageGeneratorConfig
import redis


class PresentationMakerConfig(ToolConfig):
    llm_config: LLMConfig
    image_generator_config: ImageGeneratorConfig


class PresentationToolMaker(ToolMaker):
    REQUESTED_OAUTH_INTEGRATIONS: list[str] = []
    DESCRIPTION = """The PresentationMaker ToolMaker helps generate custom presentations for users by selecting from available templates and providing structured input for automated slide creation. It simplifies building professional presentations quickly based on user instructions."""

    def __init__(
        self,
        tool_config: PresentationMakerConfig,
        platform_helper: PlatformHelper,
        oauth_integrations: dict[str, OAuthClient],
        session: Session,
        redis_client: redis.Redis,
    ):
        self.presentation_maker = PresentationMaker(
            make_template_db_manager(),
            tool_config.llm_config.to_llm(),
            ImageGenerator(
                tool_config=tool_config.image_generator_config,
                platform_helper=platform_helper,
                oauth_integrations=oauth_integrations,
                session=session,
                redis_client=redis_client,
            ),
        )
        self.platform_helper = platform_helper

    def create_ai_tools(self) -> list[BaseTool]:

        @tool
        def get_presentation_template_names():
            """Get the names of all available presentation templates."""
            template_names = ",".join(
                [
                    template.template_name
                    for template in self.presentation_maker.template_manager.get_all_templates()
                ]
            )
            return f"Templates: {template_names}"
    
        @tool
        def create_presentation(
            topic: str,
            instructions: str,
            number_of_pages: int,
            negative_prompt: str,
            template_name: str | None = None,
        ) -> str:
            """Used to create a presentation and send it to the user. Max presentation pages = 20"""
            input_obj = PresentationInput(
                topic=topic,
                instructions=instructions,
                number_of_pages=number_of_pages,
                negative_prompt=negative_prompt,
                template_name=template_name,
            )

            # Generate the presentation file path using the input object
            presentation_file_path = self.presentation_maker.make_presentation(
                presentation_input=input_obj
            )

            # Use platform helper to send the generated file
            self.platform_helper.send_file(
                file=presentation_file_path, title="Presentation.pptx"
            )

            return "Presentation created and sent to the user, tell him to see it in chat"

        return [
           get_presentation_template_names,
           create_presentation
        ]
