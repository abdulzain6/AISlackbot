from sqlalchemy import Column, LargeBinary, String
from sqlalchemy.orm import Session
from typing import TypedDict, List
from .engine import Base
import secrets



class FileUploadData(TypedDict):
    file_bytes: bytes
    file_name: str


class FileStorage(Base):
    __tablename__ = 'file_storage'
    id = Column(String, primary_key=True, unique=True, nullable=False)
    file_name = Column(String, nullable=False)
    file_data = Column(LargeBinary, nullable=False)

    @staticmethod
    def get_file_by_id(session: Session, file_id: str) -> 'FileStorage':
        try:
            file = session.query(FileStorage).filter_by(id=file_id).first()
            if not file:
                raise ValueError("File not found")
            return file
        except Exception as e:
            raise e
        finally:
            session.close()

    def upload_file_from_blob(session: Session, file_bytes: bytes, file_name: str) -> str:
        try:
            if len(file_bytes) > 1 * 1024 * 1024 * 1024:
                raise ValueError("File size exceeds 1GB limit")
            
            generated_id = secrets.token_urlsafe(32)
            new_file = FileStorage(id=generated_id, file_name=file_name, file_data=file_bytes)
            session.add(new_file)
            session.commit()
            return new_file.id
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def batch_upload_files(session: Session, files: List[FileUploadData]) -> List[str]:
        try:
            if not files:
                return []
            
            uploaded_ids = []
            for file in files:
                if len(file["file_bytes"]) > 1 * 1024 * 1024 * 1024:
                    raise ValueError(f"File size exceeds 1GB limit for file {file['file_name']}")

                generated_id = secrets.token_urlsafe(35)
                new_file = FileStorage(
                    id=generated_id,
                    file_name=file["file_name"],
                    file_data=file["file_bytes"]
                )
                session.add(new_file)
                uploaded_ids.append(generated_id)

            session.commit()
            return uploaded_ids
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
