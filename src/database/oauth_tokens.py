from typing import Optional
from sqlalchemy import Column, String, Float, Index
from sqlalchemy.orm import Session
from pydantic import BaseModel
from .engine import Base


class OAuthTokens(BaseModel):
    user_id: Optional[str] = None
    team_id: str
    app_name: str
    integration_type: str
    access_token: str
    refresh_token: str
    expires_at: float

    @property
    def doc_id(self) -> str:
        key_components = [self.team_id, self.integration_type, self.app_name]
        if self.user_id:
            key_components.append(self.user_id)
        return "_".join(key_components)

    def to_model(self):
        return OAuthTokensModel(
            doc_id=self.doc_id,
            user_id=self.user_id,
            team_id=self.team_id,
            app_name=self.app_name,
            integration_type=self.integration_type,
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            expires_at=self.expires_at,
        )

    @staticmethod
    def from_model(model: "OAuthTokensModel") -> "OAuthTokens":
        return OAuthTokens(
            user_id=model.user_id,
            team_id=model.team_id,
            app_name=model.app_name,
            integration_type=model.integration_type,
            access_token=model.access_token,
            refresh_token=model.refresh_token,
            expires_at=model.expires_at,
        )

    def save(self, session: Session) -> "OAuthTokens":
        token_model = self.to_model()
        existing_token = session.query(OAuthTokensModel).filter_by(doc_id=self.doc_id).first()
        if existing_token:
            existing_token.user_id = self.user_id
            existing_token.team_id = self.team_id
            existing_token.app_name = self.app_name
            existing_token.integration_type = self.integration_type
            existing_token.access_token = self.access_token
            existing_token.refresh_token = self.refresh_token
            existing_token.expires_at = self.expires_at
        else:
            session.add(token_model)
        session.commit()
        return self

    @staticmethod
    def delete(session: Session, team_id: str, app_name: str, integration_type: str, user_id: Optional[str] = None) -> None:
        doc_id = "_".join(filter(None, [team_id, integration_type, app_name, user_id]))
        token_model = session.query(OAuthTokensModel).filter_by(doc_id=doc_id).first()
        if token_model:
            session.delete(token_model)
            session.commit()

    @staticmethod
    def read(session: Session, team_id: str, app_name: str, integration_type: str, user_id: Optional[str] = None) -> Optional["OAuthTokens"]:
        doc_id = "_".join(filter(None, [team_id, integration_type, app_name, user_id]))
        token_model = session.query(OAuthTokensModel).filter_by(doc_id=doc_id).first()
        if token_model:
            return OAuthTokens.from_model(token_model)
        return None


class OAuthTokensModel(Base):
    __tablename__ = "oauth_tokens"
    doc_id = Column(String, primary_key=True, nullable=False)
    user_id = Column(String, nullable=True)
    team_id = Column(String, nullable=False)
    app_name = Column(String, nullable=False)
    integration_type = Column(String, nullable=False)
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=False)
    expires_at = Column(Float, nullable=False)
    __table_args__ = (
        Index("ix_team_app_integration_user_outh", "team_id", "app_name", "integration_type", "user_id"),
    )
