import logging
import os
import dotenv

from .lib.integrations.google.meets import MeetsHandler
from .lib.integrations.google.gmail import GmailHandler
from .lib.knowledge_manager import KnowledgeManager
from .lib.agent import AIAgent, FirebaseFileHandler, FirebaseListService
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from .database.oauth_tokens import FirebaseOAuthStorage
from .lib.integrations.google.google_oauth import GoogleOAuth
from .database.users import FirestoreUserStorage

dotenv.load_dotenv()
logging.basicConfig(level=logging.INFO)




handler = GmailHandler(
    FirebaseOAuthStorage("creds.json"),
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    user_id="test_user",
    team_id="test_team"
)
res = handler.send_watch_request("projects/slackbotai-60bac/topics/slackbotai-gamil")
print(res)
#exit()



manager = KnowledgeManager(
    embeddings=OpenAIEmbeddings(model="text-embedding-3-small"),
    collection_name="slackbot"
)
agent = AIAgent(
    manager, 
    ChatOpenAI(model="gpt-4o-mini"), 
    FirebaseFileHandler("slackbotai-60bac.firebasestorage.app", knowledge_manager=manager),
    list_handler=FirebaseListService(),
    token_storage=FirebaseOAuthStorage("creds.json"),
    google_client_id=os.getenv("GOOGLE_CLIENT_ID"),
    google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    google_oauth=GoogleOAuth(        
        os.getenv("SECRETS_FILE"),
        os.getenv("GOOGLE_REDIRECT_URI")
    ),
    team_id="test_team",
    user_id="test_user",
    user_storage=FirestoreUserStorage()
)

print(
    agent.chat("Gimme google signin link please")
)
