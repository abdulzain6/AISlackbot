from enum import Enum
from datetime import datetime, timedelta
from typing import Optional, List

from pydantic import BaseModel, Field
from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    String,
    select,
    update as sa_update,
    delete as sa_delete,
)
from sqlalchemy.orm import Session
from . import Base


class TaskStatusEnum(Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class AgentTaskORM(Base):
    __tablename__ = "agent_tasks"

    id = Column(String, primary_key=True, index=True)
    team_id = Column(String, nullable=False)
    platform_name = Column(String, nullable=False)
    status = Column(SAEnum(TaskStatusEnum), nullable=False)
    task_name = Column(String, nullable=False)
    description = Column(String, nullable=False)
    assigned_to = Column(String, nullable=False)
    assignee_instructions = Column(String, nullable=False)
    created_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )


class TaskStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class AgentTask(BaseModel):
    id: str
    team_id: str
    platform_name: str
    status: TaskStatus
    task_name: str
    description: str
    assigned_to: str
    assignee_instructions: str
    created_at: datetime

    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
    }

    @staticmethod
    def from_orm_model(orm_obj: AgentTaskORM) -> "AgentTask":
        # Use model_validate to create instance from ORM attributes
        return AgentTask.model_validate(orm_obj)

    def to_orm_model(self) -> AgentTaskORM:
        # Note: created_at will be set automatically by the ORM default
        data = self.model_dump(exclude={"created_at"})
        return AgentTaskORM(**data)

    @staticmethod
    def create(session: Session, **data) -> "AgentTask":
        """
        Create & persist a new AgentTask.
        created_at is set automatically.
        """
        pyd = AgentTask(**data, created_at=datetime.utcnow())
        orm_obj = pyd.to_orm_model()
        session.add(orm_obj)
        session.commit()
        session.refresh(orm_obj)
        return AgentTask.from_orm_model(orm_obj)

    @staticmethod
    def read(session: Session, task_id: str) -> Optional["AgentTask"]:
        stmt = select(AgentTaskORM).where(AgentTaskORM.id == task_id)
        orm_obj = session.scalars(stmt).first()
        return AgentTask.from_orm_model(orm_obj) if orm_obj else None

    @staticmethod
    def update(
        session: Session,
        task_id: str,
        **updates
    ) -> Optional["AgentTask"]:
        stmt = (
            sa_update(AgentTaskORM)
            .where(AgentTaskORM.id == task_id)
            .values(**updates)
            .execution_options(synchronize_session="fetch")
        )
        result = session.execute(stmt)
        if result.rowcount == 0:
            return None
        session.commit()
        return AgentTask.read(session, task_id)

    @staticmethod
    def delete(session: Session, task_id: str) -> bool:
        stmt = sa_delete(AgentTaskORM).where(AgentTaskORM.id == task_id)
        result = session.execute(stmt)
        session.commit()
        return result.rowcount > 0

    @staticmethod
    def list_by_team_and_platform(
        session: Session,
        team_id: str,
        platform_name: str,
        include_complete: bool = True
    ) -> List["AgentTask"]:
        """
        Return all tasks for a given team and platform created
        in the last 24 hours. If include_complete=False, exclude COMPLETE.
        """
        twenty_four_hrs_ago = datetime.utcnow() - timedelta(days=1)

        stmt = (
            select(AgentTaskORM)
            .where(
                AgentTaskORM.team_id == team_id,
                AgentTaskORM.platform_name == platform_name,
                AgentTaskORM.created_at >= twenty_four_hrs_ago,
            )
        )
        if not include_complete:
            stmt = stmt.where(AgentTaskORM.status != TaskStatusEnum.COMPLETE)

        orm_objs = session.scalars(stmt).all()
        return [AgentTask.from_orm_model(o) for o in orm_objs]
