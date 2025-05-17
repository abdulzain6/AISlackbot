import tempfile
import redis
from sqlalchemy.orm import Session 
from markdown_pdf import Section, MarkdownPdf
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field
from langchain_core.tools import tool, BaseTool
from ...lib.integrations.auth.oauth_handler import OAuthClient
from ...lib.platforms.platform_helper import PlatformHelper
from .tool_maker import ToolMaker, ToolConfig
from ..models.llm import LLMConfig


class Report(BaseModel):
    report_markdown: str = Field(
        ..., description="The markdown content of the report. Must have no errors."
    )
    report_css: str = Field(
        ..., description="The CSS content of the report. Must have no errors."
    )


class ReportGeneratorConfig(ToolConfig):
    llm_conf: LLMConfig
    storage_prefix: str


class ReportGenerator(ToolMaker):
    REQUESTED_OAUTH_INTEGRATIONS = []
    DESCRIPTION = """Used to make reports in PDF format and return link."""

    def __init__(
        self, 
        tool_config: ReportGeneratorConfig,
        platform_helper: PlatformHelper,
        oauth_integrations: dict[str, OAuthClient],
        session: Session,
        redis_client: redis.Redis,
    ):
        self.storage_prefix = tool_config.storage_prefix
        llm = tool_config.llm_conf.to_llm()
        self.llm = llm.with_structured_output(Report)
        self.session = session
        self.redis_client = redis_client
        self.platform_helper = platform_helper

    def generate_report(self, data: str) -> Report:
        prompt = [
            SystemMessage(
                content="""You are an experienced report writer, Write reports on the topic provided.
The report must be in markdown format. The report must be well formatted and easy to read.
The report must be well structured. The report must be well written.
The report must be well designed. The report must be well presented.
Cover all details and do not miss anything
Use easy to understand language and avoid making it too long."""
            ),
            HumanMessage(content=f"Make a report on the following data:\n {data}"),
        ]
        return self.llm.invoke(prompt)

    def report_to_pdf(self, report: Report) -> str:
        pdf = MarkdownPdf(toc_level=3)
        pdf.add_section(Section(report.report_markdown), user_css=report.report_css)
        with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as tmp_file:
            temp_path = tmp_file.name
            pdf.save(temp_path)
            self.platform_helper.send_file(temp_path, "report.pdf")

        return f"Report generated and sent to the user, tell him he can see it in chat"

    def create_ai_tools(self) -> list[BaseTool]:
        @tool
        def generate_report(
            report_topic: str,
            key_findings: str,
            further_details: str,
            executive_summary: str,
            conclusions: str,
            recommendations: str,
            appendix: str,
        ) -> str:
            """Generate a comprehensive report based on the provided unstructured research data.
            Ensure to include all relevant details without omission. Pass in all gathered data such as
            an executive summary, conclusions, recommendations, and any appendices."""

            if len(key_findings) < 100:
                return "Input data is too short; it must be at least 100 characters. Pass in all research data you did"

            report_content = (
                f"Topic: {report_topic}\n"
                f"Executive Summary: {executive_summary}\n"
                f"Key Findings for report: {key_findings}\n"
                f"Details: {further_details}\n"
                f"Conclusions: {conclusions}\n"
                f"Recommendations: {recommendations}\n"
                f"Appendix: {appendix}"
            )

            report = self.generate_report(report_content)
            link = self.report_to_pdf(report)
            return f"Report has been successfully generated and uploaded. Access it here: {link}"

        return [generate_report]

