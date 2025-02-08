import firebase_admin
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
        if not firebase_admin._apps:
            app = firebase_admin.initialize_app()
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

    def get_first_user_by_email(self, email: str) -> Optional[User]:
        query = self.collection.where('associated_google_email', '==', email).limit(1)
        results = query.get()
        for doc in results:
            return User(**doc.to_dict())
        return None

if __name__ == "__main__":
    print(FirestoreUserStorage().get_first_user_by_email("abdulzain6@gmail.com"))