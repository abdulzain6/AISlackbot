from slack_bolt import App
from slack_sdk.web import WebClient
from firebase_admin import credentials
from .lib.integrations.auth.oauth_handler import OAuthClient

import os
import dotenv, logging
import firebase_admin


dotenv.load_dotenv("src/.env")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
cred = credentials.Certificate("creds.json")
firebase_admin.initialize_app(
    cred,
    options={
        "storageBucket": os.getenv(
            "FIREBASE_STORAGE_BUCKET", "slackbotai-60bac.firebasestorage.app"
        )
    }
)
app = App(token=os.getenv("SLACK_BOT_TOKEN"))
client: WebClient = app.client

AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY")
OAUTH_INTEGRATIONS = {
    "google" : OAuthClient(
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        redirect_uri=os.getenv("GOOGLE_REDIRECT_URI"),
        auth_url="https://accounts.google.com/o/oauth2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scope=" ".join([
            "https://www.googleapis.com/auth/meetings.space.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/calendar"
        ]),
        secret_key=AUTH_SECRET_KEY
    )
}
