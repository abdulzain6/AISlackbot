from typing import Optional
from pydantic import BaseModel
from google.cloud import firestore

class APIKey(BaseModel):
    team_id: str
    app_name: str
    user_id: Optional[str] = None
    api_key: str
    integration_name: str
    metadata: dict[str, str]

    @property
    def doc_id(self) -> str:
        key_components = [self.team_id, self.integration_name, self.app_name]
        if self.user_id:
            key_components.append(self.user_id)
        return "_".join(key_components)

class APIKeyRepository:
    def __init__(self):
        self.db = firestore.Client()
        self.collection_name = "api_keys"

    def create_key(self, api_key: APIKey) -> None:
        doc_ref = self.db.collection(self.collection_name).document(api_key.doc_id)
        doc_ref.set(api_key.dict())

    def read_key(
        self,
        team_id: str,
        app_name: str,
        integration_name: str,
        user_id: Optional[str] = None,
    ) -> Optional[APIKey]:
        temp_key = APIKey(
            team_id=team_id,
            app_name=app_name,
            integration_name=integration_name,
            user_id=user_id,
            api_key="",
        )
        doc_ref = self.db.collection(self.collection_name).document(temp_key.doc_id)
        doc_snapshot = doc_ref.get()
        if doc_snapshot.exists:
            return APIKey(**doc_snapshot.to_dict())
        return None

    def update_key(self, api_key: APIKey) -> None:
        doc_ref = self.db.collection(self.collection_name).document(api_key.doc_id)
        doc_ref.update({"api_key": api_key.api_key})

    def delete_key(
        self,
        team_id: str,
        app_name: str,
        integration_name: str,
        user_id: Optional[str] = None,
    ) -> None:
        temp_key = APIKey(
            team_id=team_id,
            app_name=app_name,
            integration_name=integration_name,
            user_id=user_id,
            api_key="",
        )
        doc_ref = self.db.collection(self.collection_name).document(temp_key.doc_id)
        if doc_ref.get().exists:
            doc_ref.delete()