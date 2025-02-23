from firebase_admin import firestore
from enum import Enum
from pydantic import BaseModel
from datetime import datetime

class TaskStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class Task(BaseModel):
    team_id: str
    app_name: str
    task_name: str
    task_detail: str
    status: TaskStatus
    task_id: str
    time_created: datetime

class FirebaseUserTasks:
    def __init__(self):
        self.db = firestore.client()
        self.collection = self.db.collection('tasks')

    def create_task(self, task: Task):
        task_data = task.dict()
        task_data['time_created'] = firestore.SERVER_TIMESTAMP
        self.collection.document(task.task_id).set(task_data)

    def read_task(self, team_id: str, app_name: str, task_id: str):
        doc = self.collection \
            .where('team_id', '==', team_id) \
            .where('app_name', '==', app_name) \
            .where('task_id', '==', task_id) \
            .limit(1) \
            .stream()
        for d in doc:
            return Task(**d.to_dict())
        return None

    def update_task(self, team_id: str, app_name: str, task_id: str, task_data: dict):
        task_ref = self.collection \
            .where('team_id', '==', team_id) \
            .where('app_name', '==', app_name) \
            .where('task_id', '==', task_id) \
            .limit(1) \
            .stream()
        for d in task_ref:
            self.collection.document(d.id).update(task_data)

    def delete_task(self, team_id: str, app_name: str, task_id: str):
        task_ref = self.collection \
            .where('team_id', '==', team_id) \
            .where('app_name', '==', app_name) \
            .where('task_id', '==', task_id) \
            .limit(1) \
            .stream()
        for d in task_ref:
            self.collection.document(d.id).delete()

    def get_all_tasks_for_team(self, team_id: str, app_name: str) -> list[Task]:
        tasks = self.collection \
            .where('team_id', '==', team_id) \
            .where('app_name', '==', app_name) \
            .stream()
        return [Task(**task.to_dict()) for task in tasks]

    def update_task_status(self, team_id: str, app_name: str, task_id: str, new_status: TaskStatus):
        task_ref = self.collection \
            .where('team_id', '==', team_id) \
            .where('app_name', '==', app_name) \
            .where('task_id', '==', task_id) \
            .limit(1) \
            .stream()
        for d in task_ref:
            self.collection.document(d.id).update({"status": new_status.value})

    def get_latest_tasks_for_team(self, team_id: str, app_name: str, limit: int) -> list[Task]:
        tasks = self.collection \
            .where('team_id', '==', team_id) \
            .where('app_name', '==', app_name) \
            .order_by('time_created', direction=firestore.Query.DESCENDING) \
            .limit(limit) \
            .stream()
        return [Task(**task.to_dict()) for task in tasks]
