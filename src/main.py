import logging
import os
import re
import dotenv
import firebase_admin
from firebase_admin import credentials

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.web import WebClient
from slack_sdk.errors import SlackApiError
from langchain_openai import OpenAIEmbeddings, ChatOpenAI

from .lib.data_store import FirebaseStorageHandler

from .lib.integrations.google.gmail import GmailHandler
from .utils import get_chat_history
from .lib.knowledge_manager import KnowledgeManager
from .lib.agent import OrchestratorAgent
from .database.oauth_tokens import FirebaseOAuthStorage
from .database.gmail_watch_requests import WatchRequestStorage
from .lib.tools import get_all_tools, ToolName


dotenv.load_dotenv("src/.env")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
app = App(token=os.getenv("SLACK_BOT_TOKEN"))
client: WebClient = app.client

# Load the Firebase service account credentials
cred = credentials.Certificate("creds.json")
firebase_admin.initialize_app(
    cred,
    options={
        "storageBucket": os.getenv(
            "FIREBASE_STORAGE_BUCKET", "slackbotai-60bac.firebasestorage.app"
        )
    }
)


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

def convert_to_slack_markdown(text: str) -> str:
    # Replace [text](url) with Slack's <url|text> format.
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', lambda m: f"<{m.group(2)}|{m.group(1)}>", text)

def to_block(message: str) -> list[dict[str, str]]:
    converted_message = convert_to_slack_markdown(message.strip())
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": converted_message}},
        {"type": "divider"},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": ":sparkles: *Powered by SlackBotAI*"}]},
    ]


@app.event("message")
def handle_message_events(body):
    """Handle message events with detailed logging and thread support"""
    logging.info(f"Received message event: {body}")

    try:
        # Extract message details
        event = body.get("event", {})
        user_id = event.get("user")
        channel_id = event.get("channel")
        text = event.get("text", "")
        team_id = body.get("team_id", "")  # Extract the team ID
        thread_ts = event.get("thread_ts") or event.get(
            "ts"
        )  # Get the timestamp for threading

        logging.info(
            f"Message from user {user_id} in channel {channel_id} team {team_id}: {text}"
        )

        if (
            user_id and "bot_id" not in event and text.strip() and team_id
        ):  # Ensure message has text and not from bot
            try:
                # Fetch chat history
                history = get_chat_history(client, channel_id)
                # Initialize the KnowledgeManager
                manager = KnowledgeManager(
                    embeddings=OpenAIEmbeddings(model="text-embedding-3-small"),
                    collection_name="slackbot",
                )
                # Setup AI Agent
                agent = OrchestratorAgent(
                    ChatOpenAI(model="gpt-4o-mini"),
                    worker_tools=get_all_tools(
                        {
                            ToolName.WEB_SEARCH : {},
                            ToolName.REPORT_GENERATOR : dict(
                                llm=ChatOpenAI(model="gpt-4o-mini"),
                                storage=FirebaseStorageHandler(),
                                storage_prefix=f"{team_id}/{user_id}/",
                            )
                        }
                    ),
                    worker_llm=ChatOpenAI(model="gpt-4o"),
                    worker_message_callback=lambda response: client.chat_postMessage(
                        channel=channel_id, blocks=to_block(response)
                    ),
                )

                # Pass the received text message to the AI agent and get a response
                response = agent.run([text])
                # Send the message to the channel using blocks
                if response:
                    client.chat_postMessage(
                        channel=channel_id, blocks=to_block(response)
                    )
            except SlackApiError as e:
                logging.error(f"Error posting message: {e.response['error']}")

    except Exception as e:
        logging.error(f"Error processing message: {str(e)}", exc_info=True)


def entry_point():
    """Main function with additional error handling"""
    try:
        # Verify environment variables
        required_env_vars = ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"]
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]

        if missing_vars:
            logging.error(f"Missing required environment variables: {missing_vars}")
            return

        # Initialize and start the handler
        handler = SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN"))
        logging.info("Starting Slack bot...")
        handler.start()

    except Exception as e:
        logging.error(f"Fatal error starting bot: {str(e)}", exc_info=True)


if __name__ == "__main__":
    # check_and_renew_watch_requests()
    # schedule.every().hour.do(check_and_renew_watch_requests)
    print("Gmail Job scheduled!")
    entry_point()
