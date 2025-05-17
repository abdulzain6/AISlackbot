import os
import uuid
import redis

from io import BytesIO
from typing import List
from langchain_core.tools import tool, BaseTool
from sqlalchemy.orm import Session
from langchain_postgres import PGVector
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from ...lib.models.llm import LLMConfig
from .tool_maker import ToolMaker, ToolConfig
from ..rag.ingestion_pipeline import IngestionPipeline
from ..rag.file_convertor import FileConvertor
from ..rag.pdf_extractor import PDFExtractor
from ...database.user_files import UserFile
from ...lib.integrations.auth.oauth_handler import OAuthClient
from ...lib.platforms.platform_helper import PlatformHelper


class RAGToolConfig(ToolConfig):
    llm_conf: LLMConfig


class RAGToolMaker(ToolMaker):
    REQUESTED_OAUTH_INTEGRATIONS: list[str] = []
    DESCRIPTION = """
The ToolMaker provides a set of tools to manage and search knowledgebase documents, streamlining content retrieval and management.
It also has functions to be able to access user uploaded files.
"""

    def __init__(
        self,
        tool_config: RAGToolConfig,
        platform_helper: PlatformHelper,
        oauth_integrations: dict[str, OAuthClient],
        session: Session,
        redis_client: redis.Redis,
    ):
        self.session = session
        self.redis_client = redis_client
        self.platform_helper = platform_helper
        self.ingestion_pipeline = IngestionPipeline(
            file_convertor=FileConvertor(base_url=os.getenv("GOTENBERG_URL", "")),
            pdf_extractor=PDFExtractor(
                int(os.getenv("PDF_EXTRACTOR_SCALE", 2)),
                float(os.getenv("PDF_EXTRACTOR_MULTIPLIER", 1)),
                int(os.getenv("PDF_EXTRACTOR_MIN_DIM", 250)),
            ),
            session=self.session,
            pgvector=PGVector(
                embeddings=OpenAIEmbeddings(model="text-embedding-3-small"),
                collection_name="rag_documents",
                connection=os.getenv("DATABASE_URL", "")
            ),
            llm=tool_config.llm_conf.to_llm()
        )

    def get_team_docs(self):
        team_files = UserFile.get_files_by_team_and_platform(
            self.platform_helper.team_id,
            self.platform_helper.platform_name,
            self.session,
        )
        message = self.generate_file_list_message(team_files)
        if message:
            self.platform_helper.send_message(message)

        return [{"name": file.name, "id" : file.id} for file in team_files]

    def search_team_docs(self, query: str, name: str | None = None) -> List[Document]:
        return self.ingestion_pipeline.search_documents(
            query,
            k=int(os.getenv("RAG_SEARCH_K", 5)),
            team_id=self.platform_helper.team_id,
            platform_name=self.platform_helper.platform_name,
            name=name,
        )

    def generate_file_list_message(self, user_files: List[UserFile]) -> str | None:
        if not user_files:
            return None

        lines = ["📁 *Here are the files in the knowledgebase currently*", ""]

        for f in user_files:
            emoji = self.get_emoji_for_file(f.name)
            lines.append(f"• {emoji} *{f.name}*")

        return "\n".join(lines)

    def get_emoji_for_file(self, filename: str) -> str:
        filename = filename.lower()

        if filename.endswith(".pdf"):
            return "📄"
        elif filename.endswith((".doc", ".docx")):
            return "📝"
        elif filename.endswith((".xls", ".xlsx", ".csv")):
            return "📊"
        elif filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp")):
            return "🖼️"
        elif filename.endswith((".zip", ".rar", ".7z", ".tar", ".gz")):
            return "🗜️"
        elif filename.endswith((".mp4", ".mov", ".avi", ".mkv")):
            return "🎬"
        elif filename.endswith((".mp3", ".wav", ".aac", ".flac")):
            return "🎵"
        elif filename.endswith((".txt", ".md")):
            return "📃"
        else:
            return "📄"  # default for unknown files


    def create_ai_tools(self) -> list[BaseTool]:
        @tool
        def get_team_docs():
            """Get the list of files uploaded by the team which are already in your knowledgebase."""
            team_docs = self.get_team_docs()
            if not team_docs:
                return "No documents have added to your knowledgebase."

            return f"""
            Here are the documents uploaded by the team that are in your knowledgebase:
            {team_docs}
            ============
            The user has been sent a message with document list. So don't repeat it.
            """

        @tool
        def search_and_read_team_docs(query: str, name: str | None = None):
            """
            Gets relevent data from team uploaded files from your knowledgebase.
            Use this if you need to answer questions about the team's documents.
            Takes in name of the file to search
            """
            return self.search_team_docs(query, name)

        @tool
        def list_uploaded_files():
            """List the files uploaded lately by the user. These are not the files in knowledegbase"""
            user_files = self.platform_helper.get_recent_file_info()
            if not user_files:
                return "No files have been uploaded lately."

            return user_files

        @tool
        def add_file_to_knowledgebase(file_id: str):
            """Add a file to the knowledgebase."""
            file_bytes = self.platform_helper.get_file_bytes(file_id)
            file_name = self.platform_helper.get_file_name(file_id)
            vector_ids = self.ingestion_pipeline.ingest_file(
                BytesIO(file_bytes),
                file_name,
                self.platform_helper.team_id,
                self.platform_helper.platform_name,
            )
            UserFile(
                id=uuid.uuid4(),
                name=file_name,
                vector_ids=vector_ids,
                team_id=self.platform_helper.team_id,
                platform_name=self.platform_helper.platform_name,
            ).create(self.session)
            self.get_team_docs()
            return "File ingested into knowledgebase successfully. Now you can search for it using the search_team_docs tool and answer questions"

        @tool
        def delete_file_from_knowledgebase(filename: str):
            "Used to delete file from the knowledgebase"
            user_file = UserFile.read(
                filename,
                self.platform_helper.team_id,
                self.platform_helper.platform_name,
                self.session
            )
            if not user_file or not user_file.id:
                return f"File with name '{filename}' not found.."
            
            UserFile.delete(user_file.id, self.session)
            self.ingestion_pipeline.delete_ids(user_file.vector_ids)
            self.get_team_docs()
            return f"File deleted successfully. the user they can see the remaining files in chat an automated message was sent"
        
        return [
            get_team_docs,
            search_and_read_team_docs,
            list_uploaded_files,
            add_file_to_knowledgebase,
            delete_file_from_knowledgebase,
        ]
