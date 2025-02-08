import ipaddress
import logging
import socket
import more_itertools
import requests

from itertools import islice
from typing import Dict, List, Tuple, Union
from urllib.parse import urlparse
from extractous import Extractor, TesseractOcrConfig, PdfOcrStrategy, PdfParserConfig
from .youtube import YoutubeLoader as YouTubeLoaderNew
from google.cloud.firestore_v1.vector import Vector
from langchain.document_loaders.base import BaseLoader
from langchain.document_loaders.web_base import WebBaseLoader
from langchain.document_loaders.youtube import YoutubeLoader
from langchain.schema import Document
from langchain_google_firestore.vectorstores import FirestoreVectorStore, WRITE_BATCH_SIZE
from langchain.embeddings.base import Embeddings
from langchain.text_splitter import TokenTextSplitter




class ExtractousLoader(BaseLoader):
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def load(self):
        pdf_config = PdfParserConfig().set_ocr_strategy(PdfOcrStrategy.NO_OCR)
        extractor = Extractor().set_ocr_config(TesseractOcrConfig().set_language("eng")).set_pdf_config(pdf_config)
        return [Document(
            page_content=extractor.extract_file_to_string(self.file_path)
        )]

class FirestoreVectorStoreModified(FirestoreVectorStore):
    def _similarity_search(
        self,
        query: list[float],
        k: int = 10,  # Assuming DEFAULT_TOP_K is 10
        filters = None,
    ) -> list:
        _filters = filters or self.filters
        query_ref = self.collection  # Start with the collection

        if _filters is not None:
            for field, operation, value in _filters:
                query_ref = query_ref.where(field, operation, value)

        results = query_ref.find_nearest(
            vector_field=self.embedding_field,
            query_vector=Vector(query),
            distance_measure=self.distance_strategy,
            limit=k,
        )

        return results.get()
    
    def update_metadata(
        self,
        ids: List[str],
        metadatas: List[dict],
        **kwargs,
    ) -> List[str]:
        """Update metadata for existing documents in the vector store.

        Args:
            ids: The document ids whose metadata should be updated.
            metadatas: The new metadata values to set for each document.

        Returns:
            List[str]: The list of document ids that were updated.

        Raises:
            ValueError: If no ids provided, lengths don't match, or documents not found.
        """
        if len(ids) == 0:
            raise ValueError("No document ids provided to update metadata.")

        if len(ids) != len(metadatas):
            raise ValueError(
                "The length of metadatas must be the same as the length of ids."
            )

        # Verify all documents exist first
        missing_docs = []
        for doc_id in ids:
            doc_ref = self.collection.document(doc_id)
            if not doc_ref.get().exists:
                missing_docs.append(doc_id)
        
        if missing_docs:
            raise ValueError(
                f"The following documents were not found: {', '.join(missing_docs)}"
            )

        db_batch = self.client.batch()
        updated_ids: List[str] = []

        # Update in batches to stay within Firestore limits
        for batch in more_itertools.chunked(zip(ids, metadatas), WRITE_BATCH_SIZE):
            for doc_id, metadata in batch:
                doc = self.collection.document(doc_id)
                db_batch.update(doc, {self.metadata_field: metadata})
                updated_ids.append(doc_id)
            
            db_batch.commit()
            db_batch = self.client.batch()  # Create new batch for next chunk

        return updated_ids

class KnowledgeManager:
    def __init__(
        self,
        embeddings: Embeddings,
        chunk_size: int = 1200,
        collection_name: str = "slackbot"
    ) -> None:
        self.embeddings = embeddings
        self.chunk_size = chunk_size
        self.vectorstore = FirestoreVectorStoreModified(
            collection=collection_name,
            embedding_service=embeddings,
        )        

    def update_metadata(self, ids: list, metadata: dict):
        self.vectorstore.update_metadata(ids, metadatas=[metadata] * len(ids))

    def load_data(self, file_path: str) -> Tuple[str, List[Document], bytes]:
        print(f"Loading {file_path}")
        
        if not file_path.startswith("/tmp/"):
            logging.error(f"Invalid file path: {file_path}. Access outside /tmp directory is not allowed.")
            raise ValueError("Invalid file path")

        loader = ExtractousLoader(
            file_path=file_path,
        )
        docs = loader.load_and_split(text_splitter=TokenTextSplitter(chunk_size=self.chunk_size))  
        logging.info(f"Loaded {len(docs)} Documents.")
        contents = "\n\n".join([doc.page_content for doc in docs])

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        return contents, docs, file_bytes
    
    def injest_data(self, documents: List[Document]) -> List[str]:
        if not documents:
            raise ValueError("No documents provided")

        content = "".join(doc.page_content for doc in documents if doc.page_content)
        if len(content) <= 7:
            raise ValueError("Insufficient data in documents")
        
        batch_size = 150
        ids = []
        
        iterator = iter(documents)
        while True:
            batch = list(islice(iterator, batch_size))
            if not batch:
                break
            
            try:
                batch_ids = self.vectorstore.add_documents(batch)
                ids.extend(batch_ids)
            except Exception as e:
                print(f"Error adding batch: {str(e)}")
        
        if not ids:
            raise ValueError("No documents were successfully added to the vectorstore")
        
        return ids

    def add_metadata_to_docs(self, metadata: Dict, docs: List[Document]):
        for document in docs:
            document.metadata.update(metadata)
        return docs

    def load_and_injest_file(
        self, filepath: str, metadata: Dict
    ) -> Tuple[str, List[str], bytes]:
        contents, docs, file_bytes = self.load_data(filepath)
        docs = self.add_metadata_to_docs(metadata=metadata, docs=docs)
        ids = self.injest_data(documents=docs)
        return contents, ids, file_bytes

    def is_local_ip(self, ip: str) -> bool:
        try:
            return ipaddress.ip_address(ip).is_private
        except ValueError:
            return False

    def validate_url(self, url: str) -> bool:
        allowed_schemes = ["http", "https"]

        parsed_url = urlparse(url)

        if parsed_url.scheme not in allowed_schemes:
            print("Invalid URL scheme")
            return False

        try:
            ip = socket.gethostbyname(parsed_url.hostname)
            if self.is_local_ip(ip):
                print("Local IPs are not allowed")
                return False
        except (socket.gaierror, TypeError):
            print("Invalid domain")
            return False

        return True

    def is_site_working(self, url: str) -> bool:
        """
        Checks if a given URL is working by sending a request and checking the status code.

        :param url: URL of the site to check.
        :return: True if the site is working, False otherwise.
        """
        try:
            response = requests.get(url, timeout=5, allow_redirects=True)
            return response.status_code == 200
        except requests.RequestException:
            return False
        
    def is_youtube_video(self, url: str) -> bool:
        try:
            YoutubeLoader.extract_video_id(url)
            logging.info("It is yt video")
            return True
        except Exception as e:
            logging.info(f"It is not yt video {e}")
            return False

    def _format_url(self, url: str) -> str:
        """Clean and format URL"""
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        return url

    def load_url_content(self, url: str, metadata: Dict = None) -> Tuple[str, List, bytes]:
        """
        Load content from a URL, automatically detecting if it's a YouTube video or web page.
        
        Args:
            url: The URL to load content from
            metadata: Optional metadata to add to the documents
            
        Returns:
            Tuple containing:
            - content as string
            - list of document IDs
            - content as bytes
        """
        # Clean and validate URL
        url = self._format_url(url)
        if not self.validate_url(url):
            raise ValueError("Invalid URL provided")
            
        try:
            if self.is_youtube_video(url):
                loader = YouTubeLoaderNew(video_url=url)
                logging.info("Using YouTube loader")
            else:
                loader = WebBaseLoader(
                    web_path=url,
                    requests_kwargs={"timeout": 10, "allow_redirects": True}
                )
                logging.info("Using web page loader")
            
            # Load and process content
            docs = loader.load_and_split(text_splitter=TokenTextSplitter(chunk_size=self.chunk_size))

            # Extract and validate content
            content = "".join([doc.page_content for doc in docs])
            if not content or "YouTubeAboutPressCopyrightContact" in content:
                raise ValueError("No valid content found in URL")
                
            # Add metadata if provided
            if metadata:
                docs = self.add_metadata_to_docs(metadata, docs)
            
            # Store documents and return results
            doc_ids = self.injest_data(docs)
            return content, doc_ids, content.encode('utf-8')
            
        except Exception as e:
            import traceback
            traceback.print_exception(e)
            logging.error(f"Error processing URL {url}: {str(e)}")
            raise ValueError(f"Failed to process URL: {str(e)}")

    def delete_ids(self, ids: list[str]):
        if ids:
            return self.vectorstore.delete(ids)

    @staticmethod
    def create_filters(criteria: Dict[str, Union[str, List[str]]]) -> List[Tuple[str, str, Union[str, List[str]]]]:
        filters = []
        for key, value in criteria.items():
            if isinstance(value, list):
                filters.append((f'metadata.{key}', 'in', value))
            else:
                filters.append((f'metadata.{key}', '==', value))
        return filters

    def query_data(
        self, query: str, k: int, metadata: Dict[str, str] = None
    ):
        try:
            return self.vectorstore.similarity_search(query, k, filters=self.create_filters(metadata))
        except Exception as e:
            print(f"error retrieving: {e}")
            return []

