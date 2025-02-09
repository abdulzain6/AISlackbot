from firebase_admin import firestore
from typing import Optional
from pydantic import BaseModel

class OAuthTokens(BaseModel):
    user_id: str
    team_id: str
    integration_type: str
    access_token: str
    refresh_token: str
    expires_at: float


class FirebaseOAuthStorage:
    def __init__(self):
        self.db: firestore.Client = firestore.client()

    def _make_key(self, user_id: str, team_id: str, integration_type: str) -> str:
        return f"{user_id}_{team_id}_{integration_type}"

    def store_or_update_tokens(self, tokens: OAuthTokens) -> None:
        doc_ref = self.db.collection('oauth_tokens').document(self._make_key(tokens.user_id, tokens.team_id, tokens.integration_type))
        doc_ref.set(tokens.model_dump(), merge=True)

    def get_tokens(self, user_id: str, team_id: str, integration_type: str) -> Optional[OAuthTokens]:
        doc_ref = self.db.collection('oauth_tokens').document(self._make_key(user_id, team_id, integration_type))
        doc = doc_ref.get()
        if doc.exists:
            return OAuthTokens(**doc.to_dict())
        else:
            return None

    def delete_tokens(self, user_id: str, team_id: str, integration_type: str) -> None:
        doc_ref = self.db.collection('oauth_tokens').document(self._make_key(user_id, team_id, integration_type))
        doc_ref.delete()

    def get_all_user_tokens(self, user_id: str, team_id: str) -> list[OAuthTokens]:
        docs = self.db.collection('oauth_tokens').where('user_id', '==', user_id).where('team_id', '==', team_id).stream()
        return [OAuthTokens(**doc.to_dict()) for doc in docs]
