from pydantic import BaseModel
from google.cloud import firestore
from typing import Optional

class User(BaseModel):
    user_id: str
    team_name: str
    associated_google_email: Optional[str] = None
    user_name: Optional[str] = None


class FirestoreUserStorage:
    def __init__(self):
        self.db = firestore.Client()
        self.collection = self.db.collection('users')

    def _get_unique_id(self, user: User) -> str:
        return f"{user.team_name}_{user.user_id}"

    def upsert_user(self, user: User) -> None:
        unique_id = self._get_unique_id(user)
        self.collection.document(unique_id).set(user.dict(), merge=True)

    def get_user(self, team_name: str, user_id: str) -> Optional[User]:
        unique_id = f"{team_name}_{user_id}"
        doc = self.collection.document(unique_id).get()
        if doc.exists:
            return User(**doc.to_dict())
        return None

    def delete_user(self, team_name: str, user_id: str) -> None:
        unique_id = f"{team_name}_{user_id}"
        self.collection.document(unique_id).delete()
