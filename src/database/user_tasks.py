from firebase_admin import firestore, storage
from enum import Enum
from pydantic import BaseModel


class TaskStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Task(BaseModel):
    team_id: str
    task_name: str
    task_detail: str
    status: TaskStatus
    task_id: str


class FirebaseUserTasks:
    def __init__(self):
        self.db = firestore.client()
        self.collection = self.db.collection('tasks')

    def create_task(self, task: Task):
        self.collection.document(task.task_id).set(task.model_dump())

    def read_task(self, task_id: str):
        doc = self.collection.document(task_id).get()
        if doc.exists:
            return Task(**doc.to_dict())
        return None

    def update_task(self, task_id: str, task_data: dict):
        self.collection.document(task_id).update(task_data)

    def delete_task(self, task_id: str):
        self.collection.document(task_id).delete()

    def get_all_tasks_for_user(self, user_id: str):
        tasks = self.collection.where('user_id', '==', user_id).stream()
        return [Task(**task.to_dict()) for task in tasks]

    def update_task_status(self, task_id: str, new_status: TaskStatus):
        self.collection.document(task_id).update({"status": new_status.value})
