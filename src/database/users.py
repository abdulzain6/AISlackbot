from sqlalchemy import Column, String, Index
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from .engine import Base


class UserModel(Base):
    __tablename__ = "users"
    app_name = Column(String, primary_key=True)
    app_team_id = Column(String, primary_key=True)
    app_user_id = Column(String, primary_key=True)
    associated_google_email = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_app_name", "app_name"),
        Index("idx_app_team_id", "app_team_id"),
        Index("idx_app_user_id", "app_user_id"),
    )


class User(BaseModel):
    app_team_id: str
    app_user_id: str
    app_name: str
    associated_google_email: Optional[str] = None

    def upsert_user(self, session: Session) -> 'User':
        user_data = (
            session.query(UserModel)
            .filter_by(
                app_name=self.app_name,
                app_team_id=self.app_team_id,
                app_user_id=self.app_user_id,
            )
            .first()
        )
        if user_data:
            user_data.associated_google_email = self.associated_google_email
        else:
            new_user = UserModel(
                app_name=self.app_name,
                app_team_id=self.app_team_id,
                app_user_id=self.app_user_id,
                associated_google_email=self.associated_google_email,
            )
            session.add(new_user)
        session.commit()
        return self

    @staticmethod
    def get_user(
        session: Session, app_name: str, app_team_id: str, app_user_id: str
    ) -> Optional["User"]:
        user_data = (
            session.query(UserModel)
            .filter_by(
                app_name=app_name, app_team_id=app_team_id, app_user_id=app_user_id
            )
            .first()
        )
        if user_data:
            return User(
                app_name=user_data.app_name,
                app_team_id=user_data.app_team_id,
                app_user_id=user_data.app_user_id,
                associated_google_email=user_data.associated_google_email,
            )
        return None

    @staticmethod
    def delete_user(
        session: Session, app_name: str, app_team_id: str, app_user_id: str
    ) -> None:
        session.query(UserModel).filter_by(
            app_name=app_name, app_team_id=app_team_id, app_user_id=app_user_id
        ).delete()
        session.commit()

    @staticmethod
    def update_associated_google_email(
        session: Session,
        app_name: str,
        app_team_id: str,
        app_user_id: str,
        new_email: str,
    ) -> None:
        user_data = (
            session.query(UserModel)
            .filter_by(
                app_name=app_name, app_team_id=app_team_id, app_user_id=app_user_id
            )
            .first()
        )
        if user_data:
            user_data.associated_google_email = new_email
            session.commit()
