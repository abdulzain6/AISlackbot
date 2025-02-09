import firebase_admin
from firebase_admin import firestore
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any



class WatchRequestStorage:
    def __init__(self) -> None:
        self.db: firestore.Client = firestore.client()

    def update_expiration(self, user_id: str, team_id: str, topic_name: str, expiration_millis: float) -> None:
        doc_ref: firestore.DocumentReference = self.db.collection('gmail_watch_expiration').document(f"{team_id}_{user_id}")
        doc_ref.set({
            'topic_name': topic_name,
            'expiration': expiration_millis
        }, merge=True)

    def get_expiry_for_user(self, user_id: str, team_id: str) -> Optional[Dict[str, Any]]:
        doc_ref: firestore.DocumentReference = self.db.collection('gmail_watch_expiration').document(f"{team_id}_{user_id}")
        doc: firestore.DocumentSnapshot = doc_ref.get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        if 'expiration' in data:
            data['expiration'] = datetime.fromtimestamp(data['expiration'] / 1000.0)
        return data
    
    def get_soon_to_expire_topics(self, hours_until_expiration: int = 1) -> List[Tuple[str, Dict[str, Any]]]:
        current_time: datetime = datetime.utcnow()
        expiry_time_millis = int((current_time + timedelta(hours=hours_until_expiration)).timestamp() * 1000)
        docs: firestore.DocumentSnapshot = self.db.collection('gmail_watch_expiration').where('expiration', '<=', expiry_time_millis).stream()
        return [(doc.id, doc.to_dict()) for doc in docs]

def test_firestore_storage():
    storage = WatchRequestStorage()
    user_id = "test_user"
    team_id = "test_team"
    topic_name = "test_topic"
    expiration = datetime.utcnow() + timedelta(days=1)

    storage.update_expiration(user_id, team_id, topic_name, expiration)
    saved_data = storage.get_expiry_for_user(user_id, team_id)
    assert saved_data is not None
    assert saved_data['topic_name'] == topic_name
    assert int(saved_data['expiration'].timestamp() * 1000) == int(expiration.timestamp() * 1000)
    non_existent_data = storage.get_expiry_for_user("non_existent_user", "non_existent_team")
    assert non_existent_data is None

    soon_to_expire_topics = storage.get_soon_to_expire_topics(hours_until_expiration=24)
    assert any(user_id in topic[0] for topic in soon_to_expire_topics)

if __name__ == "__main__":
    test_firestore_storage()