from firebase_admin import firestore
from typing import Optional
from pydantic import BaseModel


class OAuthTokens(BaseModel):
    user_id: Optional[str] = None
    team_id: str
    app_name: str
    integration_type: str
    access_token: str
    refresh_token: str
    expires_at: float


class TokenRequest(BaseModel):
    user_id: Optional[str] = None
    team_id: str 
    app_name: str
    integration_type: str


class FirebaseOAuthStorage:
    def __init__(self):
        self.db: firestore.Client = firestore.client()

    def _make_key(
        self, token: TokenRequest
    ) -> str:
        return f"{token.user_id}_{token.team_id}_{token.app_name}_{token.integration_type}"

    def store_or_update_tokens(self, tokens: OAuthTokens) -> None:
        doc_ref = self.db.collection("oauth_tokens").document(
            self._make_key(
                TokenRequest(
                    user_id=tokens.user_id,
                    team_id=tokens.team_id,
                    app_name=tokens.app_name,
                    integration_type=tokens.integration_type,
                )
            )
        )
        doc_ref.set(tokens.model_dump(), merge=True)

    def get_tokens(
        self, 
        token_request: TokenRequest
    ) -> Optional[OAuthTokens]:
        doc_ref = self.db.collection("oauth_tokens").document(
            self._make_key(token_request)
        )
        doc = doc_ref.get()
        if doc.exists:
            return OAuthTokens(**doc.to_dict())
        else:
            return None

    def delete_tokens(
        self, token_request: TokenRequest
    ) -> None:
        doc_ref = self.db.collection("oauth_tokens").document(
            self._make_key(token_request)
        )
        doc_ref.delete()
