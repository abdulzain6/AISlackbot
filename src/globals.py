from slack_bolt import App
from slack_sdk.web import WebClient
from .lib.integrations.auth.oauth_handler import OAuthClient
import dotenv, logging, os


dotenv.load_dotenv("src/.env")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
app = App(
    signing_secret=os.getenv("SLACK_SIGNING_SECRET"),
    token=os.getenv("SLACK_APP_TOKEN"),
)
client: WebClient = app.client

AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY")
OAUTH_INTEGRATIONS = {
    "google": OAuthClient(
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        redirect_uri=os.getenv("GOOGLE_REDIRECT_URI"),
        auth_url="https://accounts.google.com/o/oauth2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scope=" ".join(
            [
                "https://www.googleapis.com/auth/meetings.space.readonly",
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/calendar.events",
                "https://www.googleapis.com/auth/calendar",
            ]
        ),
        secret_key=AUTH_SECRET_KEY,
    ),
    "slack": OAuthClient(
        client_id=os.getenv("SLACK_CLIENT_ID"),
        client_secret=os.getenv("SLACK_CLIENT_SECRET"),
        redirect_uri=os.getenv("SLACK_REDIRECT_URI", "https://localhost:3000"),
        auth_url="https://slack.com/oauth/v2/authorize",
        token_url="https://slack.com/api/oauth.v2.access",
        scope=" ".join(
            [
                "app_mentions:read",
                "assistant:write",
                "calls:read",
                "channels:history",
                "channels:read",
                "chat:write",
                "files:read",
                "files:write",
                "im:history",
                "im:read",
                "im:write",
                "im:write.topic",
                "links:read",
                "metadata.message:read",
                "mpim:history",
                "mpim:read",
                "mpim:write",
                "reminders:write",
                "team:read",
                "users.profile:read",
                "users:read",
                "users:read.email",
                "search:read"
            ]
        ),
        secret_key=AUTH_SECRET_KEY,
    ),
}
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/3")
