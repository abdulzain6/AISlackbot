from pydantic import BaseModel
from google.cloud import firestore
from typing import Optional

class User(BaseModel):
    user_id: str
    app_team_name: str
    app_user_id: str
    associated_google_email: Optional[str] = None

class FirestoreUserStorage:
    def __init__(self):
        self.db = firestore.Client()
        self.collection = self.db.collection('users')

    def upsert_user(self, user: User) -> None:
        self.collection.document(user.user_id).set(user.model_dump(), merge=True)

    def get_user(self, user_id: str) -> Optional[User]:
        doc = self.collection.document(user_id).get()
        if doc.exists:
            return User(**doc.to_dict())
        return None

    def get_user_by_app_user_id_and_team(self, app_user_id: str, app_team_name: str) -> Optional[User]:
        query = self.collection.where('app_user_id', '==', app_user_id).where('app_team_name', '==', app_team_name)
        docs = query.get()
        for doc in docs:
            return User(**doc.to_dict())
        return None

    def delete_user(self, user_id: str) -> None:
        self.collection.document(user_id).delete()