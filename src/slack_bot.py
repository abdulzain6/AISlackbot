import logging
import os
import uuid

from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError
from langchain_openai import OpenAIEmbeddings, ChatOpenAI

from .lib.tools.serializeable_llm import LLMConfig
from .lib.knowledge_manager import KnowledgeManager
from .lib.agents.orchestrator import OrchestratorAgent
from .lib.agents.worker import WorkerConfig
from .database.users import User, FirestoreUserStorage
from .lib.tools import get_all_tools, ToolName
from .lib.platforms.slack import get_chat_history, send_message_to_slack, SendMessageConfig
from .lib.platforms import Platform
from .lib.tasks import perform_task
from .globals import client, app



@app.event("message")
def handle_message_events(body):
    """Handle message events with detailed logging and thread support"""
    """Handle message events with detailed logging and thread support, including bot mention detection"""
    logging.info(f"Received message event: {body}")

    try:
        # Extract message details
        event = body.get("event", {})
        user_id = event.get("user")
        channel_id = event.get("channel")
        text = event.get("text", "")
        team_id = body.get("team_id", "")
        thread_ts = event.get("thread_ts") or event.get("ts")
        is_direct_message = channel_id.startswith("D")
        bot_id = body.get("authorizations", [{}])[0].get("user_id", "")
        bot_mentioned = f"<@{bot_id}>" in text if bot_id else False


        logging.info(
            f"Message from user {user_id} in channel {channel_id} team {team_id}: {text}"
        )

        if (
            user_id and "bot_id" not in event and text.strip() and team_id
        ):  # Ensure message has text and not from bot
            try:

                history = get_chat_history(client, channel_id)
                manager = KnowledgeManager(
                    embeddings=OpenAIEmbeddings(model="text-embedding-3-small"),
                    collection_name="slackbot",
                )
                user = FirestoreUserStorage().get_user_by_app_user_id_and_team(
                    user_id, team_id
                )
                if not user:
                    user = User(
                        user_id=uuid.uuid4().hex,
                        app_team_name=team_id,
                        app_user_id=user_id,
                    )
                    FirestoreUserStorage().upsert_user(user)

                # Setup AI Agent
                worker_tools_dict = {
                    ToolName.WEB_SEARCH : {},
                    ToolName.REPORT_GENERATOR : dict(
                        llm_conf=LLMConfig(
                            model_provider="openai",
                            model="gpt-4o-mini",
                            llm_kwargs={}
                        ),
                        storage_prefix=f"slack/{user.app_team_name}/{user.app_user_id}/",
                    )
                }
                worker_tools = get_all_tools(worker_tools_dict)

                def worker_runner(task_name: str, task_detail: str, task_id: str):
                    perform_task.apply_async(
                        kwargs=dict(
                            task_name=task_name,
                            task_detail=task_detail,
                            task_id=task_id,
                            user=user,
                            platform=Platform.SLACK,
                            send_message_config=SendMessageConfig(
                                channel_id=channel_id,
                                thread_ts=thread_ts,
                            ),
                            worker_config=WorkerConfig(
                                worker_tools_dict=worker_tools_dict,
                                worker_llm_config={"model" : "gpt-4o"},
                                worker_additional_info=""
                            ),
                        ),
                        task_id=task_id,
                    )
                agent = OrchestratorAgent(
                    llm=ChatOpenAI(model="gpt-4o-mini"),
                    run_worker_task=worker_runner,
                    disable_checker=is_direct_message or bot_mentioned,
                    worker_tools=worker_tools
                )

                response = agent.run([text])
                if response:
                    send_message_to_slack(channel_id, response, thread_ts)

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
