from .lib.integrations.google.gmail import GmailHandler
from .database.oauth_tokens import FirebaseOAuthStorage
from .database.gmail_watch_requests import WatchRequestStorage
import os

def check_and_renew_watch_requests():
    storage = WatchRequestStorage()
    soon_to_expire_topics = storage.get_soon_to_expire_topics(hours_until_expiration=1)

    for doc_id, data in soon_to_expire_topics:
        user_id, team_id = doc_id.split("_")
        topic_name = data["topic_name"]
        print(
            f"Renewing watch request for user: {user_id}, team: {team_id}, topic: {topic_name}"
        )
        watcher = GmailHandler(
            token_storage=FirebaseOAuthStorage("creds.json"),
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            user_id=user_id,
            team_id=team_id,
        )
        data = watcher.send_watch_request(user_id, team_id, topic_name)
        storage.update_expiration(
            user_id=user_id,
            team_id=team_id,
            topic_name=topic_name,
            expiration_millis=data["expiration"],
        )

