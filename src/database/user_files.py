from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy import ARRAY, Column, String, Index
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import UUID
import uuid
from . import Base


class UserFileORM(Base):
    __tablename__ = "user_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True)
    vector_ids = Column(ARRAY(String))
    team_id = Column(String, nullable=False)
    platform_name = Column(String, nullable=False)

    __table_args__ = (
        Index("ix_team_id_platform_name", "team_id", "platform_name"),
    )


class UserFile(BaseModel):
    id: Optional[uuid.UUID] = None
    name: str
    vector_ids: List[str]
    team_id: str
    platform_name: str

    def create(self, session: Session):
        orm_instance = self.to_orm_model()
        session.add(orm_instance)
        session.commit()
        self.id = orm_instance.id
        return self

    @staticmethod
    def read(name: str, team_id: str, platform_name: str, session: Session):
        orm_instance = session.query(UserFileORM).filter_by(
            name=name, team_id=team_id, platform_name=platform_name
        ).first()
        if orm_instance:
            return UserFile.from_orm_model(orm_instance)
        return None

    def update(self, session: Session):
        orm_instance = session.query(UserFileORM).filter_by(id=self.id).first()
        if orm_instance:
            orm_instance.name = self.name
            orm_instance.vector_ids = self.vector_ids
            orm_instance.team_id = self.team_id
            orm_instance.platform_name = self.platform_name
            session.commit()
            return UserFile.from_orm_model(orm_instance)
        return None

    @staticmethod
    def delete(file_id: uuid.UUID, session: Session):
        orm_instance = session.query(UserFileORM).filter_by(id=file_id).first()
        if orm_instance:
            session.delete(orm_instance)
            session.commit()
            return True
        return False

    @staticmethod
    def get_files_by_team_and_platform(team_id: str, platform_name: str, session: Session):
        orm_instances = session.query(UserFileORM).filter_by(
            team_id=team_id, platform_name=platform_name
        ).all()
        return [UserFile.from_orm_model(instance) for instance in orm_instances]

    def to_orm_model(self):
        return UserFileORM(
            id=self.id or uuid.uuid4(),
            name=self.name,
            vector_ids=self.vector_ids,
            team_id=self.team_id,
            platform_name=self.platform_name,
        )

    @classmethod
    def from_orm_model(cls, orm_model: UserFileORM):
        return cls(
            id=orm_model.id,
            name=orm_model.name,
            vector_ids=orm_model.vector_ids if orm_model.vector_ids else [],
            team_id=orm_model.team_id,
            platform_name=orm_model.platform_name,
        )
