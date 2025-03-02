from pydantic import BaseModel
from firebase_admin import firestore
from typing import Optional, List


class SlackToken(BaseModel):
    team_id: str
    team_name: str
    bot_user_id: str
    bot_access_token: str
    is_enterprise_install: bool = False


class FirebaseSlackTokenStorage:
    def __init__(self):
        self.db: firestore.Client = firestore.client()
        self.collection = self.db.collection('slack_tokens')

    def upsert_token(self, token: SlackToken) -> None:
        """Save or update a token using team_id as the unique identifier"""
        self.collection.document(token.team_id).set(token.dict())

    def get_token(self, team_id: str) -> Optional[SlackToken]:
        """Retrieve a token by team_id"""
        doc = self.collection.document(team_id).get()
        if doc.exists:
            return SlackToken(**doc.to_dict())
        return None

    def delete_token(self, team_id: str) -> None:
        """Delete a token by team_id"""
        self.collection.document(team_id).delete()