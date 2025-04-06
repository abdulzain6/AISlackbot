import logging
from typing import Optional
from pydantic import BaseModel
from sqlalchemy import Column, String, JSON, Index
from sqlalchemy.orm import Session
from .engine import Base



class APIKey(BaseModel):
    team_id: str
    app_name: str
    user_id: Optional[str] = None
    api_key: str
    integration_name: str
    metadata: dict[str, str] = {}

    @property
    def doc_id(self) -> str:
        key_components = [self.team_id, self.integration_name, self.app_name]
        if self.user_id:
            key_components.append(self.user_id)
        doc_id = "_".join(key_components)
        logging.info(f"Doc id: {doc_id}")
        return doc_id

    def to_model(self):
        return APIKeyModel(
            team_id=self.team_id,
            app_name=self.app_name,
            user_id=self.user_id,
            api_key=self.api_key,
            integration_name=self.integration_name,
            meta_data=self.metadata,
        )

    @staticmethod
    def from_model(model: "APIKeyModel"):
        return APIKey(
            team_id=model.team_id,
            app_name=model.app_name,
            user_id=model.user_id,
            api_key=model.api_key,
            integration_name=model.integration_name,
            metadata=model.meta_data,
        )

    def save(self, session: Session) -> 'APIKeyModel':
        api_key_model = self.to_model()
        api_key_model.doc_id = self.doc_id
        existing_key = session.query(APIKeyModel).filter_by(doc_id=self.doc_id).first()
        if existing_key:
            existing_key.team_id = self.team_id
            existing_key.app_name = self.app_name
            existing_key.user_id = self.user_id
            existing_key.api_key = self.api_key
            existing_key.integration_name = self.integration_name
            existing_key.meta_data = self.metadata
        else:
            session.add(api_key_model)
        session.commit()
        return self

    def delete(self, session: Session) -> None:
        api_key_model = session.query(APIKeyModel).filter_by(doc_id=self.doc_id).first()
        if api_key_model:
            session.delete(api_key_model)
            session.commit()

    @staticmethod
    def read(
        session: Session,
        team_id: str,
        app_name: str,
        integration_name: str,
        user_id: Optional[str] = None,
    ) -> Optional["APIKey"]:
        doc_id = "_".join(filter(None, [team_id, integration_name, app_name, user_id]))
        api_key_model = session.query(APIKeyModel).filter_by(doc_id=doc_id).first()
        if api_key_model:
            return APIKey.from_model(api_key_model)
        return None


class APIKeyModel(Base):
    __tablename__ = "api_keys"

    doc_id = Column(String, primary_key=True, nullable=False)
    team_id = Column(String, nullable=False)
    app_name = Column(String, nullable=False)
    user_id = Column(String, nullable=True)
    api_key = Column(String, nullable=False)
    integration_name = Column(String, nullable=False)
    meta_data = Column(JSON, default=dict)  # Retain the "metadata" field as is

    __table_args__ = (
        Index("ix_team_app_integration_user", "team_id", "app_name", "integration_name", "user_id"),
    )
