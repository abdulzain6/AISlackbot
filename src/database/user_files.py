import itertools
import os
import tempfile
import logging
import hashlib

from firebase_admin import firestore, storage
from typing import List, Optional, Dict
from pydantic import BaseModel
from enum import Enum
from io import BytesIO
from datetime import datetime, timedelta
from langchain.tools import tool
from ..lib.knowledge_manager import KnowledgeManager

class FileSource(Enum):
    DOCUMENT = "DOCUMENT"
    LINK = "LINK"


class UserFile(BaseModel):
    file_name: str
    firebase_storage_reference: str
    vector_ids: list[str]
    user_id: str
    team_id: str
    file_source: FileSource
    link: Optional[str] = None
    doc_id: Optional[str] = None
    is_private: bool = False  # Default to False - visible to team


class FirebaseFileHandler:
    def __init__(self, knowledge_manager: KnowledgeManager):
        self.knowledge_manager = knowledge_manager
        self.bucket = storage.bucket()
        self.collection = firestore.client().collection('user_files')

    def create_user_file(self, user_file: UserFile, file_data: bytes) -> str:
        """
        Upload file to Firebase Storage and create a new user file document in Firestore.
        
        Args:
            user_file: UserFile model instance
            file_data: Bytes of the file to upload
            
        Returns:
            str: Document ID of created record
            
        Raises:
            Exception: If file upload or document creation fails
        """
        try:
            user_file_dict = user_file.model_dump()

            # Generate a unique file path in storage
            if user_file.file_source != FileSource.LINK:
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                file_hash = hashlib.md5(file_data).hexdigest()[:8]
                storage_path = f"{user_file.team_id}/{user_file.user_id}/{timestamp}_{file_hash}_{user_file.file_name}"
                
                # Upload file to Firebase Storage
                blob = self.bucket.blob(storage_path)
                blob.upload_from_string(
                    file_data,
                    content_type=self._get_content_type(user_file.file_name)
                )
                
                # Update the UserFile model with storage reference
                user_file_dict['firebase_storage_reference'] = storage_path

            user_file_dict['file_source'] = user_file.file_source.value
            user_file_dict['created_at'] = firestore.SERVER_TIMESTAMP
            user_file_dict['updated_at'] = firestore.SERVER_TIMESTAMP
            
            # Create Firestore document
            doc_ref = self.collection.document()
            doc_ref.set(user_file_dict)
            
            logging.info(f"Created user file document with ID: {doc_ref.id}")
            return doc_ref.id
            
        except Exception as e:
            logging.error(f"Failed to create user file: {str(e)}")
            # Clean up the uploaded file if Firestore document creation fails
            if 'blob' in locals():
                try:
                    blob.delete()
                except Exception as delete_error:
                    logging.error(f"Failed to delete uploaded file after error: {str(delete_error)}")
            raise

    def generate_download_url(self, storage_path: str, expiration_minutes: int = 15) -> str:
        """
        Generate a temporary signed URL for downloading a file.
        
        Args:
            storage_path: Path to the file in Firebase Storage
            expiration_minutes: Number of minutes until the URL expires
            
        Returns:
            str: Signed URL for downloading the file
        """
        blob = self.bucket.blob(storage_path)
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="GET"
        )
        return url

    def _get_content_type(self, filename: str) -> str:
        """
        Determine content type based on file extension.
        
        Args:
            filename: Name of the file
            
        Returns:
            str: MIME type for the file
        """
        extension = filename.lower().split('.')[-1]
        content_types = {
            'pdf': 'application/pdf',
            'txt': 'text/plain',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'csv': 'text/csv',
            'json': 'application/json',
        }
        return content_types.get(extension, 'application/octet-stream')

    def get_user_file(self, doc_id: str) -> Optional[UserFile]:
        """
        Retrieve a user file document by ID.
        
        Args:
            doc_id: Document ID to retrieve
            
        Returns:
            Optional[UserFile]: UserFile instance if found, None otherwise
        """
        try:
            doc_ref = self.collection.document(doc_id)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                # Convert string back to Enum
                data['file_source'] = FileSource(data['file_source'])
                # Remove timestamp fields for Pydantic model
                data.pop('created_at', None)
                data.pop('updated_at', None)
                return UserFile(**data)
            
            logging.info(f"No user file found with ID: {doc_id}")
            return None
            
        except Exception as e:
            logging.error(f"Failed to retrieve user file: {str(e)}")
            raise

    def update_user_file(self, doc_id: str, updates: Dict[str, any]) -> bool:
        """
        Update specific fields of a user file document.
        
        Args:
            doc_id: Document ID to update
            updates: Dictionary of fields to update and their new values
            
        Returns:
            bool: True if update successful, False otherwise
        """
        try:
            doc_ref = self.collection.document(doc_id)
            
            # Convert Enum to string if present
            if 'file_source' in updates and isinstance(updates['file_source'], FileSource):
                updates['file_source'] = updates['file_source'].value
            
            updates['updated_at'] = firestore.SERVER_TIMESTAMP
            doc_ref.update(updates)
            
            logging.info(f"Updated user file document: {doc_id}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to update user file: {str(e)}")
            return False

    def delete_user_file(self, doc_id: str) -> bool:
        """
        Delete a user file document and its associated storage file.
        
        Args:
            doc_id: Document ID to delete
            
        Returns:
            bool: True if deletion successful, False otherwise
        """
        try:
            # Get the document first to get storage reference
            doc = self.get_user_file(doc_id)
            if doc:
                # Delete from Storage if reference exists
                if doc.firebase_storage_reference:
                    blob = self.bucket.blob(doc.firebase_storage_reference)
                    blob.delete()
                
                # Delete from Firestore
                self.collection.document(doc_id).delete()
                
                logging.info(f"Deleted user file document and storage: {doc_id}")
                return True
            
            return False
            
        except Exception as e:
            logging.error(f"Failed to delete user file: {str(e)}")
            return False

    def list_user_files(self, user_id: str, team_id: Optional[str] = None) -> List[UserFile]:
        """
        List all user files for a specific user and optionally team.
        Files marked as private will only be visible to their owner.
        
        Args:
            user_id: User ID to filter by
            team_id: Optional team ID to filter by
            
        Returns:
            List[UserFile]: List of UserFile instances
        """
        try:
            if team_id:
                # First query: Get all files owner by the user in this team
                own_files = self.collection\
                    .where(filter=firestore.FieldFilter("team_id", "==", team_id))\
                    .where(filter=firestore.FieldFilter("user_id", "==", user_id))\
                    .stream()

                # Second query: Get all non-private team files
                team_files = self.collection\
                    .where(filter=firestore.FieldFilter("team_id", "==", team_id))\
                    .where(filter=firestore.FieldFilter("is_private", "==", False))\
                    .stream()

                # Process both result sets, using a set to avoid duplicates
                seen_ids = set()
                user_files = []
                
                # Process all files
                for doc in itertools.chain(own_files, team_files):
                    if doc.id not in seen_ids:
                        seen_ids.add(doc.id)
                        data = doc.to_dict()
                        data['file_source'] = FileSource(data['file_source'])
                        if not data.get("doc_id"):
                            data["doc_id"] = doc.id
                        user_files.append(UserFile(**data))
            else:
                # If no team_id, just get user's own files
                docs = self.collection\
                    .where(filter=firestore.FieldFilter("user_id", "==", user_id))\
                    .stream()
                
                user_files = []
                for doc in docs:
                    data = doc.to_dict()
                    data['file_source'] = FileSource(data['file_source'])
                    if not data.get("doc_id"):
                        data["doc_id"] = doc.id
                    user_files.append(UserFile(**data))
            
            logging.info(f"Retrieved {len(user_files)} user files")
            return user_files
            
        except Exception as e:
            logging.error(f"Failed to list user files: {str(e)}")
            raise
        
    def is_file_accessible(self, doc_id: str, user_id: str, team_id) -> bool:
        """
        Check if a file is accessible to a specific user.
        A file is accessible if:
        1. The user owns the file OR
        2. The file is in user's team AND is not private
        
        Args:
            doc_id: Document ID of the file
            user_id: ID of the user trying to access the file
            
        Returns:
            bool: True if the user can access the file, False otherwise
            
        Raises:
            Exception: If there's an error checking file access
        """
        try:
            doc = self.get_user_file(doc_id)
            
            if not doc:
                logging.warning(f"File {doc_id} not found")
                return False
                        
            # User owns the file - always allow access
            if doc.user_id == user_id:
                return True
                
            # If file is private and user is not owner, deny access
            if doc.team_id == team_id and not doc.is_private:
                return True
                
            # If user is in same team and file is not private, allow access
            return False
            
        except Exception as e:
            logging.error(f"Error checking file access: {str(e)}")
            raise

    def delete_file(self, doc_id: str, user_id: str, team_id: str):
        file = self.get_user_file(doc_id=doc_id)
        if not file:
            raise ValueError("File does not exist.")
        
        if file.user_id != user_id and file.team_id != team_id:
            raise ValueError("File is not owned by the user. Only owners can delete files.")
        
        self.knowledge_manager.delete_ids(file.vector_ids)
        self.delete_user_file(doc_id)

    def add_file(
        self,        
        is_private: bool,
        user_id: str,
        team_id: str,
        file: Optional[BytesIO] = None,
        link: Optional[str] = None,
        metadata: dict = None,
    ):
        if not file and not link:
            raise ValueError('Either a link must be provided or a file must be uploaded (Ask the user if a file is expected)')

        if not metadata:
            metadata = {}

        doc_id = None

        metadata["user_id"] = user_id
        metadata["team_id"] = team_id
        try:
            if file:
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    try:
                        metadata["filename"] = file.name

                        file.seek(0)
                        temp_file.write(file.read())
                        temp_file.flush()
                        
                        # Process the file using the knowledge manager
                        contents, ids, file_bytes = self.knowledge_manager.load_and_injest_file(
                            filepath=temp_file.name,
                            metadata=metadata
                        )
                        doc_id = self.create_user_file(
                            user_file=UserFile(
                                file_contents=contents,
                                firebase_storage_reference="",
                                vector_ids=ids,
                                user_id=user_id,
                                team_id=team_id,
                                file_source=FileSource.DOCUMENT,
                                file_name=file.name,
                                is_private=is_private
                            ),
                            file_data=file_bytes
                        )
                        metadata["doc_id"] = doc_id
                        self.knowledge_manager.update_metadata(ids, metadata=metadata)

                    finally:
                        try:
                            os.unlink(temp_file.name)
                        except OSError:
                            pass  # Handle case where file is already deleted

            if link:
                metadata["filename"] = link
                contents, ids, file_bytes = self.knowledge_manager.load_url_content(link, metadata)
                doc_id = self.create_user_file(
                    user_file=UserFile(
                        file_contents=contents,
                        firebase_storage_reference="",
                        vector_ids=ids,
                        user_id=user_id,
                        team_id=team_id,
                        file_source=FileSource.LINK,
                        file_name=link,
                        link=link,
                        is_private=is_private
                    ),
                    file_data=file_bytes
                )
                metadata["doc_id"] = doc_id
                self.knowledge_manager.update_metadata(ids, metadata=metadata)        
        except Exception as e:
            if doc_id:
                self.delete_user_file(doc_id)
            raise e

    def list_accessbile_files(self, user_id: str, team_id: str):
        "Used to list files currently available in the knowledgebase to the user private or team files"
        files = self.list_user_files(user_id=user_id, team_id=team_id)
        if not files:
            return "The user has no files in their team or their private repo"
        file_string = "Knowledgebase: "
        for file in files:
            file_string += f"""
=================
Filename : {file.file_name}
Filetype : {file.file_source.value}
doc_id: {file.doc_id}
Is Private : {file.is_private} (False means its a team file)
=================
"""         
        return file_string
    
    def create_ai_tools(self, user_id: str, team_id: str, file: Optional[BytesIO] = None):
        @tool
        def delete_file(doc_id: str):
            "Used to remove data from the knowledgebase"
            try:
                self.delete_file(doc_id=doc_id, team_id=team_id, user_id=user_id)
                return "Data deleted from knowledgebase"
            except Exception as e:
                return f"Failed to delete data: Error: {e} "

        @tool
        def read_data(doc_id: str, query: str):
            "Used to read data, It only gets relevant data to the query from the file. Use this to answer questions. doc_id can be obtained by list_accessible_files"
            if not self.is_file_accessible(doc_id=doc_id, user_id=user_id, team_id=team_id):
                return "File does not exist."
            
            return self.knowledge_manager.query_data(query, k=3, metadata={"doc_id": doc_id, "team_id": team_id, "user_id": user_id})

        @tool
        def list_accessible_files():
            "Used to list files currently available in the knowledgebase to the user private or team files"
            return self.list_accessbile_files(user_id, team_id)

        @tool
        def ingest_data(link: Optional[str] = None, is_document: bool = False, is_private: bool = True):
            """Used to ingest data to the knowledgebase. Data can be from a link or a document. If it's a link pass in the link if not just set is_document to true. If a document is not private, team members can see it as well."""
            
            if not link and not is_document:
                return "Either link or document must be provided."
            
            if not file and not link:
                return "User has not uploaded a file recently, Ask them to upload a file so we can ingest the latest one."

            try:
                self.add_file(
                    user_id=user_id, team_id=team_id, file=file, link=link, is_private=is_private
                )
            except Exception as e:
                return f"Error in uploading file: {e}"

            return "File successfully added!"

        return [delete_file, read_data, list_accessible_files, ingest_data]