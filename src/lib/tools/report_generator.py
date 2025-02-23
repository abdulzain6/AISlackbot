import tempfile
import os
import uuid
from markdown_pdf import Section, MarkdownPdf
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field
from langchain_core.tools import tool, Tool
from .tool_maker import ToolMaker, ToolConfig
from ..data_store import FirebaseStorageHandler
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel


class Report(BaseModel):
    report_markdown: str = Field(
        ..., description="The markdown content of the report. Must have no errors."
    )
    report_css: str = Field(
        ..., description="The CSS content of the report. Must have no errors."
    )


class LLMConfig(BaseModel):
    model_provider: str
    model: str
    llm_kwargs: dict[str, str] = {}

    def to_llm(self) -> BaseChatModel:
        init_params = {
            "model_provider": self.model_provider,
            "model": self.model,
            **self.llm_kwargs
        }
        llm = init_chat_model(**init_params)
        return llm


class ReportGeneratorConfig(ToolConfig):
    llm_conf: LLMConfig
    storage_prefix: str
    storage: FirebaseStorageHandler = None

    class Config:
        arbitrary_types_allowed = True


class ReportGenerator(ToolMaker):
    def __init__(
        self, tool_config: ReportGeneratorConfig
    ):
        self.storage_prefix = tool_config.storage_prefix
        llm = tool_config.llm_conf.to_llm()
        self.llm = llm.with_structured_output(Report)
        if not tool_config.storage:
            tool_config.storage = FirebaseStorageHandler()

        self.storage = tool_config.storage

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

        # Save to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            temp_path = tmp_file.name
            pdf.save(temp_path)
        # Upload to the storage and get the link
        try:
            link = self.storage.upload_file(
                temp_path, self.storage_prefix + f"{uuid.uuid4()}.pdf"
            )
        finally:
            os.remove(temp_path)  # Clean up the temporary file

        return link

    def create_ai_tools(self) -> list[Tool]:
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


def main():
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model="gpt-4o")

    storage = FirebaseStorageHandler()  # Replace with actual initialization

    report_generator = ReportGenerator(
        llm=llm, storage=storage, storage_prefix="test/reports/"
    )

    # Sample data for report generation
    sample_data = "Make report on tesla stock"
    report = report_generator.generate_report(sample_data)

    # Create PDF and upload
    storage_link = report_generator.report_to_pdf(report)
    print(f"Report uploaded to: {storage_link}")


# This block prevents `main` from running if the script is imported
if __name__ == "__main__":
    main()
