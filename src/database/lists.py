import logging
from typing import Optional, List as PyList, Tuple
from pydantic import BaseModel
from sqlalchemy import Column, String, JSON, Boolean, Index, ARRAY
from sqlalchemy.orm import Session
from .engine import Base


class List(BaseModel):
    user_id: str
    team_id: str
    list_name: str
    list_contents: PyList[str]
    is_private: bool
    metadata: Optional[dict] = {}

    @property
    def doc_id(self) -> str:
        doc_id = f"{self.team_id}_{self.list_name}_{self.user_id}"
        logging.info(f"Generated doc_id: {doc_id}")
        return doc_id

    def to_model(self) -> "ListModel":
        return ListModel(
            doc_id=self.doc_id,
            user_id=self.user_id,
            team_id=self.team_id,
            list_name=self.list_name,
            list_contents=self.list_contents,
            is_private=self.is_private,
            meta_data=self.metadata or {}
        )

    @staticmethod
    def from_model(model: "ListModel") -> "List":
        return List(
            user_id=model.user_id,
            team_id=model.team_id,
            list_name=model.list_name,
            list_contents=model.list_contents,
            is_private=model.is_private,
            metadata=model.meta_data,
        )

    def save(self, session: Session) -> "ListModel":
        list_model = self.to_model()
        existing_list = session.query(ListModel).filter_by(doc_id=self.doc_id).first()
        if existing_list:
            existing_list.user_id = self.user_id
            existing_list.team_id = self.team_id
            existing_list.list_name = self.list_name
            existing_list.list_contents = self.list_contents
            existing_list.is_private = self.is_private
            existing_list.meta_data = self.metadata
        else:
            session.add(list_model)
        session.commit()
        return list_model

    def delete(self, session: Session) -> bool:
        list_model = session.query(ListModel).filter_by(doc_id=self.doc_id).first()
        if list_model:
            session.delete(list_model)
            session.commit()
            return True
        return False
            
    @staticmethod
    def read(session: Session, list_id: str, user_id: str, team_id: str) -> Optional["List"]:
        if not list_id.startswith(f"{team_id}_"):
            return None
        list_model = session.query(ListModel).filter_by(doc_id=list_id).first()
        if list_model and list_model.team_id == team_id:
            if list_model.is_private and list_model.user_id != user_id:
                return None
            return List.from_model(list_model)
        return None
            
    @staticmethod
    def read_all(session: Session, user_id: str, team_id: str) -> PyList["List"]:
        user_lists = session.query(ListModel).filter_by(team_id=team_id, user_id=user_id).all()
        public_lists = session.query(ListModel).filter(
            ListModel.team_id == team_id,
            ListModel.is_private == False,
            ListModel.user_id != user_id
        ).all()
        all_lists = user_lists + public_lists
        return [List.from_model(list_model) for list_model in all_lists]

    def add_item(self, session: Session, item: str) -> bool:
        list_model = session.query(ListModel).filter_by(doc_id=self.doc_id).first()
        if list_model and list_model.user_id == self.user_id:
            if item not in list_model.list_contents:
                list_model.list_contents.append(item)
                session.commit()
                return True
        return False

    def remove_item(self, session: Session, index: int) -> Tuple[bool, Optional[str]]:
        list_model = session.query(ListModel).filter_by(doc_id=self.doc_id).first()
        if list_model and list_model.user_id == self.user_id:
            try:
                item = list_model.list_contents.pop(index)
                session.commit()
                return True, item
            except IndexError:
                return False, None
        return False, None


class ListModel(Base):
    __tablename__ = "lists"

    doc_id = Column(String, primary_key=True, nullable=False)
    user_id = Column(String, nullable=False)
    team_id = Column(String, nullable=False)
    list_name = Column(String, nullable=False)
    list_contents = Column(ARRAY(String), default=list)
    is_private = Column(Boolean, nullable=False, default=True)
    meta_data = Column(JSON, default=dict)

    __table_args__ = (
        Index("ix_team_user_listname", "team_id", "user_id", "list_name", unique=True),
    )
