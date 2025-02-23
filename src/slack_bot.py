import logging
import os
import uuid

from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from .lib.tools.report_generator import LLMConfig
from .lib.knowledge_manager import KnowledgeManager
from .lib.agents.orchestrator import OrchestratorAgent
from .lib.agents.worker import WorkerConfig
from .database.users import User, FirestoreUserStorage
from .database.user_tasks import FirebaseUserTasks
from .lib.tools import get_all_tools, ToolName
from .lib.platforms.slack import (
    get_chat_history,
    send_message_to_slack,
    SendMessageConfig,
)
from .lib.platforms import Platform
from .lib.tasks import perform_task
from .globals import client, app


@app.event("message")
def handle_message_events(body):
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

        if user_id and "bot_id" not in event and text.strip() and team_id:
            try:

                history = get_chat_history(client, channel_id, 10, thread_ts=thread_ts)

                user = FirestoreUserStorage().get_user(
                    "slack", team_id, user_id
                )
                if not user:
                    user = User(
                        app_team_id=team_id,
                        app_user_id=user_id,
                        app_name="slack"
                    )
                    FirestoreUserStorage().upsert_user(user)

                # Setup AI Agent
                worker_tools_dict = {
                    ToolName.WEB_SEARCH: {},
                    ToolName.REPORT_GENERATOR: dict(
                        llm_conf=LLMConfig(
                            model_provider="openai", model="gpt-4o-mini", llm_kwargs={}
                        ),
                        storage_prefix=f"slack/{user.app_team_id}/{user.app_user_id}/",
                    ),
                    ToolName.GOOGLE_MEETS: {
                        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                        "user_id": user.app_user_id,
                        "team_id": user.app_team_id,
                        "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI"),
                        "platform": Platform.SLACK,
                    },
                    ToolName.GOOGLE_OAUTH: {
                        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                        "user_id": user.app_user_id,
                        "team_id": user.app_team_id,
                        "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI"),
                        "platform": Platform.SLACK,
                    },
                }

                orchestrator_tools_dict = {
                    ToolName.TEAM_TASKS: {"team_id": team_id, "platform" : Platform.SLACK},
                }

                worker_tools = get_all_tools(worker_tools_dict)
                orchestrator_tools = get_all_tools(orchestrator_tools_dict)

                tasks = FirebaseUserTasks().get_latest_tasks_for_team(user.app_team_id, "slack", 5)
                task_list = '\n'.join(f"{i+1}. {task.task_name}" for i, task in enumerate(tasks))
                orchestrator_additional_info = f"""
============================
Here is what you have already done. (Avoid duplicates):
{task_list}
============================
"""

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
                                worker_llm_config={"model": "gpt-4o-2024-11-20"},
                                worker_additional_info="",
                            ),
                        ),
                        task_id=task_id,
                    )

                agent = OrchestratorAgent(
                    llm=ChatOpenAI(model="gpt-4o-2024-11-20"),
                    run_worker_task=worker_runner,
                    disable_checker=is_direct_message or bot_mentioned,
                    worker_tools=worker_tools,
                    orchestrator_tools=orchestrator_tools,
                    additional_info=orchestrator_additional_info,
                )

                response = agent.run(
                    [
                        f'{message["display_name"]}: {message["message"]}'
                        for message in history
                    ]
                )
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
