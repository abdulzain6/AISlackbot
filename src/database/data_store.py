from sqlalchemy import Column, LargeBinary, String
from sqlalchemy.orm import Session
from uuid import uuid4
from .engine import Base
import secrets


class FileStorage(Base):
    __tablename__ = 'file_storage'
    id = Column(String, primary_key=True, unique=True, nullable=False)
    file_name = Column(String, nullable=False)
    file_data = Column(LargeBinary, nullable=False)

    def upload_file(session: Session, local_file_path: str) -> str:
        try:
            with open(local_file_path, "rb") as file:
                file_data = file.read()
                if len(file_data) > 1 * 1024 * 1024 * 1024:
                    raise ValueError("File size exceeds 1GB limit")

                generated_id = secrets.token_urlsafe(32)
                file_name = local_file_path.split("/")[-1]
                new_file = FileStorage(id=generated_id, file_name=file_name, file_data=file_data)
                session.add(new_file)
                session.commit()
                return new_file.id
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

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