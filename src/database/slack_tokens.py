from sqlalchemy import Column, String, JSON, Index
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from .engine import Base

class SlackToken(BaseModel):
    team_id: str
    team_name: str
    bot_user_id: str
    bot_access_token: str
    is_enterprise_install: bool = False

    @property
    def doc_id(self) -> str:
        return self.team_id

    def to_model(self) -> "SlackTokenModel":
        return SlackTokenModel(
            team_id=self.team_id,
            team_name=self.team_name,
            bot_user_id=self.bot_user_id,
            bot_access_token=self.bot_access_token,
            is_enterprise_install=self.is_enterprise_install,
        )

    @staticmethod
    def from_model(model: "SlackTokenModel") -> "SlackToken":
        return SlackToken(
            team_id=model.team_id,
            team_name=model.team_name,
            bot_user_id=model.bot_user_id,
            bot_access_token=model.bot_access_token,
            is_enterprise_install=model.is_enterprise_install,
        )

    def save(self, session: Session) -> "SlackTokenModel":
        slack_token_model = self.to_model()
        existing_entry = session.query(SlackTokenModel).filter_by(team_id=self.doc_id).first()
        if existing_entry:
            existing_entry.team_name = self.team_name
            existing_entry.bot_user_id = self.bot_user_id
            existing_entry.bot_access_token = self.bot_access_token
            existing_entry.is_enterprise_install = self.is_enterprise_install
        else:
            session.add(slack_token_model)
        session.commit()
        return self

    def delete(self, session: Session) -> None:
        existing_entry = session.query(SlackTokenModel).filter_by(team_id=self.doc_id).first()
        if existing_entry:
            session.delete(existing_entry)
            session.commit()

    @staticmethod
    def read(session: Session, team_id: str) -> Optional["SlackToken"]:
        model_instance = session.query(SlackTokenModel).filter_by(team_id=team_id).first()
        if model_instance:
            return SlackToken.from_model(model_instance)
        return None


class SlackTokenModel(Base):
    __tablename__ = "slack_tokens"
    team_id = Column(String, primary_key=True, nullable=False)
    team_name = Column(String, nullable=False)
    bot_user_id = Column(String, nullable=False)
    bot_access_token = Column(String, nullable=False)
    is_enterprise_install = Column(JSON, default=False)

    __table_args__ = (Index("ix_team_id", "team_id"),)
