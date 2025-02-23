from pydantic import BaseModel
from google.cloud import firestore
from typing import Optional

class User(BaseModel):
    app_team_id: str
    app_user_id: str
    app_name: str
    associated_google_email: Optional[str] = None

class FirestoreUserStorage:
    def __init__(self):
        self.db = firestore.Client()
        self.collection = self.db.collection('users')

    def upsert_user(self, user: User) -> None:
        doc_id = f"{user.app_name}_{user.app_team_id}_{user.app_user_id}"
        self.collection.document(doc_id).set(user.model_dump(), merge=True)

    def get_user(self, app_name: str, app_team_id: str, app_user_id: str) -> Optional[User]:
        doc_id = f"{app_name}_{app_team_id}_{app_user_id}"
        doc = self.collection.document(doc_id).get()
        if doc.exists:
            return User(**doc.to_dict())
        return None

    def delete_user(self, app_name: str, app_team_id: str, app_user_id: str) -> None:
        doc_id = f"{app_name}_{app_team_id}_{app_user_id}"
        self.collection.document(doc_id).delete()

    def update_associated_google_email(self, app_name: str, app_team_id: str, app_user_id: str, new_email: str) -> None:
        doc_id = f"{app_name}_{app_team_id}_{app_user_id}"
        self.collection.document(doc_id).update({'associated_google_email': new_email})