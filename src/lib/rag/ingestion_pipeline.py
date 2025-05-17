import base64
import os
import uuid
from PIL import Image
from io import BytesIO
from sqlalchemy.orm import Session
from .file_convertor import FileConvertor
from .pdf_extractor import PDFExtractor
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel
from langchain_postgres import PGVector
from langchain_text_splitters import CharacterTextSplitter
from langchain_core.documents import Document
from ...database.data_store import FileStorage, FileUploadData


class IngestionPipeline:
    def __init__(
        self,
        file_convertor: FileConvertor,
        pgvector: PGVector,
        pdf_extractor: PDFExtractor,
        session: Session,
        llm: BaseChatModel
    ):
        self.file_convertor = file_convertor
        self.pgvector = pgvector
        self.pdf_extractor = pdf_extractor
        self.session = session
        self.llm = llm

    def ingest_file(
        self,
        file_bytes_io: BytesIO,
        file_name: str,
        team_id: str,
        platform_name: str
    ) -> list[str]:
        # Supported formats
        supported_file_types = {
            # Office and document formats
            ".123", ".602", ".abw", ".bib", ".cdr", ".cgm", ".cmx", ".csv", ".cwk", ".dbf",
            ".dif", ".doc", ".docm", ".docx", ".dot", ".dotm", ".dotx", ".dxf", ".emf", ".eps",
            ".epub", ".fodg", ".fodp", ".fods", ".fodt", ".fopd", ".htm", ".html", ".hwp",
            ".key", ".ltx", ".lwp", ".mcw", ".met", ".mml", ".mw", ".numbers", ".odd", ".odg",
            ".odm", ".odp", ".ods", ".odt", ".otg", ".oth", ".otp", ".ots", ".ott", ".pages",
            ".pdf", ".pot", ".potm", ".potx", ".pps", ".ppt", ".pptm", ".pptx", ".psw", ".pub",
            ".rtf", ".sda", ".sdc", ".sdd", ".sdp", ".sdw", ".sgl", ".slk", ".smf", ".stc",
            ".std", ".sti", ".stw", ".svg", ".svm", ".swf", ".sxc", ".sxd", ".sxg", ".sxi",
            ".sxm", ".sxw", ".txt", ".uof", ".uop", ".uos", ".uot", ".vdx", ".vor", ".vsd",
            ".vsdm", ".vsdx", ".wb2", ".wk1", ".wks", ".wpd", ".wps", ".xhtml", ".xls", ".xlsb",
            ".xlsm", ".xlsx", ".xlt", ".xltm", ".xltx", ".xlw", ".xml", ".zabw",
            # Image extensions
            ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff"
        }

        text_based_formats = {".json", ".txt", ".csv", ".xml", ".yaml", ".yml", ".log"}

        # Extract extension
        root, file_extension = os.path.splitext(file_name)
        ext_lower = file_extension.lower()

        if ext_lower not in supported_file_types:
            raise ValueError(f"Unsupported file type {ext_lower} for file {file_name}")

        documents = []

        # Handle image files: convert any to JPEG and summarize
        if ext_lower in {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff"}:
            # Load image from BytesIO
            img = Image.open(file_bytes_io)
            # Convert to RGB (for formats with alpha)
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            # Save to JPEG buffer
            buf = BytesIO()
            img.save(buf, format="JPEG")
            jpeg_bytes = buf.getvalue()
            # Base64 for LLM prompt
            base64_image = base64.b64encode(jpeg_bytes).decode('utf-8')

            # Invoke LLM summarization
            result = self.llm.invoke(
                [
                    SystemMessage(content="You are to summarize the images provided to you in detail"),
                    HumanMessage(
                        content=[
                            {"type": "text", "text": "Summarize the image provided in detail."},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ],
                    )
                ]
            )
            summary = result.content
            documents.append(
                Document(
                    page_content=str(summary),
                    metadata={
                        "file_name": file_name,
                        "team_id": team_id,
                        "platform_name": platform_name,
                        "images": FileStorage.batch_upload_files(
                            session=self.session,
                            files=[
                                FileUploadData(
                                    file_name=f"{uuid.uuid4()}_{uuid.uuid4()}.png",
                                    file_bytes=jpeg_bytes,
                                )
                            ],
                        ),
                    }
                )
            )
        elif ext_lower in text_based_formats:
            # Text-based read and store
            file_content = file_bytes_io.read().decode("utf-8")
            documents.append(
                Document(
                    page_content=file_content,
                    metadata={
                        "file_name": file_name,
                        "team_id": team_id,
                        "platform_name": platform_name
                    }
                )
            )
        else:
            # Convert other docs to PDF and extract
            converted_bytes_io = self.file_convertor.convert_to_pdf(
                file_bytes_io, ext_lower
            )
            extracted_data = self.pdf_extractor.extract_pages(converted_bytes_io)

            for data in extracted_data:
                documents.append(
                    Document(
                        page_content=data.text,
                        metadata={
                            "page_number": data.page_number + 1,
                            "images": FileStorage.batch_upload_files(
                                session=self.session,
                                files=[
                                    FileUploadData(
                                        file_name=f"{uuid.uuid4()}_{uuid.uuid4()}.png",
                                        file_bytes=image,
                                    ) for image in data.images
                                ],
                            ),
                            "page_images": FileStorage.batch_upload_files(
                                session=self.session,
                                files=[
                                    FileUploadData(
                                        file_name=f"{uuid.uuid4()}_{uuid.uuid4()}.png",
                                        file_bytes=image,
                                    ) for image in data.page_images
                                ],
                            ),
                            "file_name": file_name,
                            "team_id": team_id,
                            "platform_name": platform_name,
                        },
                    )
                )

        # Split and add to PGVector
        return self.pgvector.add_documents(
            CharacterTextSplitter(chunk_size=20000).split_documents(documents)
        )

    def search_documents(
        self, 
        query: str, 
        k: int = 5, 
        team_id: str | None = None, 
        platform_name: str | None = None,
        name: str | None = None
    ):
        filter_dict = {}
        if team_id is not None:
            filter_dict["team_id"] = {"$eq": team_id}
        if platform_name is not None:
            filter_dict["platform_name"] = {"$eq": platform_name}
        if name is not None:
            filter_dict["file_name"] = {"$eq": name}

        filter_arg = filter_dict if filter_dict else None

        return self.pgvector.similarity_search(query, k=k, filter=filter_arg)

    def delete_ids(self, ids: list[str]):
        self.pgvector.delete(ids)