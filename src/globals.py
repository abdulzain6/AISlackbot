from slack_bolt import App
from slack_sdk.web import WebClient
from firebase_admin import credentials

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