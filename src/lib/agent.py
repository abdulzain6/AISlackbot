from datetime import datetime

from typing import Optional
from io import BytesIO
from langchain.schema import BaseMessage
from langchain.chat_models.base import BaseChatModel
from langchain.prompts.chat import ChatPromptTemplate
from langchain.agents import AgentExecutor, create_tool_calling_agent
from ..database.oauth_tokens import FirebaseOAuthStorage

from ..lib.integrations.google.meets import create_ai_tools_for_meets
from ..lib.integrations.google.calendar import create_ai_tools_for_calendar
from ..lib.integrations.google.gmail import create_ai_tools_for_gmail, GmailHandler

from .integrations.google.google_oauth import GoogleOAuth
from ..database.user_files import FirebaseFileHandler
from ..database.lists import FirebaseListService
from ..database.users import User, FirestoreUserStorage
from ..database.gmail_watch_requests import WatchRequestStorage
from .knowledge_manager import KnowledgeManager

class AIAgent:
    def __init__(
        self,
        knowledge_manager: KnowledgeManager,
        llm: BaseChatModel,
        firebase_file_handler: FirebaseFileHandler,
        list_handler: FirebaseListService,
        google_oauth: GoogleOAuth,
        token_storage: FirebaseOAuthStorage,
        user_storage: FirestoreUserStorage,
        watch_request_storage: WatchRequestStorage,
        google_client_id: str,
        google_client_secret: str,
        team_id: str,
        user_id: str,
        topic_name_gmail: str,
        user_name: str = None,
        prompt: ChatPromptTemplate = None
    ) -> None:
        self.token_storage = token_storage
        self.google_client_id = google_client_id
        self.google_client_secret = google_client_secret
        self.knowledge_manager = knowledge_manager
        self.llm = llm
        self.firebase_file_handler = firebase_file_handler
        self.list_handler = list_handler
        self.prompt = prompt
        self.team_id = team_id
        self.user_id = user_id
        self.google_oauth = google_oauth

        if not user_storage.get_user(team_name=team_id, user_id=user_id):
            user_storage.upsert_user(
                User(
                    user_id=user_id,
                    team_name=team_id,
                    associated_google_email=None,
                    user_name=user_name
                )
            )
        
        if not watch_request_storage.get_expiry_for_user(user_id=user_id, team_id=team_id):
            try:
                gmail_handler = GmailHandler(
                    token_storage=self.token_storage,
                    client_id=self.google_client_id,
                    client_secret=self.google_client_secret,
                    user_id=self.user_id,
                    team_id=self.team_id
                )
                data = gmail_handler.send_watch_request(topic_name_gmail)
                watch_request_storage.update_expiration(user_id, team_id, topic_name_gmail, data["expiration"])
            except Exception as e:
                pass

        if not prompt:
            self.prompt = ChatPromptTemplate([
                ("system", """You are SlackAI, An AI assistant developed to assist slack team members and help with productivity.
    There are many functions which you can perform to help the users.
    1. Answer questions from the user files/links.
    You can read user data to answer questions from them (RAG).
    User data can be user files or team files (accessible to other team members aswell).
    Data can be links or documents. Data must be ingested first before it can be used.
    2. You can also create lists for the user, They can also be private or accessible to other team members. Lists can be of anything... websites, github repos etc.
    You can use then find relavent information from these lists if asked to. Dont add to the list unless confirmed by the user to.
        
    User currently has the following data in the knowledgebase:
    {files}
    =================
    User has the following lists saved:
    {lists}
    =================
    Additional Notes:
    {day_info}
    All dates are in UTC the tools also expect utc.
    Avoid mentioning techical information like IDs. Use simple language, so simple that even a child understands (important)
    Avoid giving raw information. Try to properly format it so its readable.
    Be as useful as possible use your tools to full extent to make yourself useful.
    If youre sending an email don't add placeholders to it, it leaves a bad impression. simply reword the message or as the user more info. 
    If youre replying to an email, make sure to read the conversation before replying to get context
                 """),
                ("placeholder", "{chat_history}"),
                ("human", "{input}"),
                ("placeholder", "{agent_scratchpad}"),
            ])


    def chat(self, message: str, file: Optional[BytesIO] = None, chat_history: list[BaseMessage] = []):
        file_tools = self.firebase_file_handler.create_ai_tools(user_id=self.user_id, team_id=self.team_id, file=file)
        google_services = [
            ('meets', create_ai_tools_for_meets),
            ('calendar', create_ai_tools_for_calendar),
            ('gmail', create_ai_tools_for_gmail)
        ]

        google_tools = []
        for service, create_tools_func in google_services:
            tools = create_tools_func(
                token_storage=self.token_storage,
                client_id=self.google_client_id,
                client_secret=self.google_client_secret,
                user_id=self.user_id,
                team_id=self.team_id
            )
            google_tools.extend(tools)

        google_oauth_tools = self.google_oauth.create_ai_tools(user_id=self.user_id, team_id=self.team_id)
        tools = [*file_tools, *google_oauth_tools, *self.list_handler.create_ai_tools(team_id=self.team_id, user_id=self.user_id), *google_tools]
        agent = create_tool_calling_agent(self.llm, tools, self.prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
        return agent_executor.invoke(
            {
                "input": message,
                "chat_history" : chat_history,
                "files" : self.firebase_file_handler.list_accessbile_files(self.user_id, self.team_id),
                "lists" : self.list_handler.get_lists(self.user_id, self.team_id),
                "day_info" : f"Today is {datetime.utcnow().strftime('%A, %B %d, %Y %I:%M %p UTC')}"
            }
        )["output"]

