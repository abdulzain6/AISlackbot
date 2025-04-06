import json
import logging
import os
import re
import time
import redis

from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError
from .lib.event_handlers import FORM_EVENT_HANDLERS
from .lib.tools.report_generator import LLMConfig
from .lib.agents.worker import WorkerConfig
from .database.users import User
from .database.slack_tokens import SlackToken
from .database.engine import SessionLocal
from .lib.tools import ToolName
from .lib.platforms.slack import SlackHelper
from .lib.platforms import Platform
from .lib.tasks import perform_task
from .globals import app, REDIS_URL


@app.event("message")
def handle_message_events(body):
    """Handle message events with detailed logging, time tracking, and thread support, including bot mention detection"""
    start_time = time.time()  # Track the start time for execution
    logging.info("Event received: Processing message event")
    session = SessionLocal()

    try:
        process_start_time = time.time()
        # Extract message details
        event = body.get("event", {})
        user_id = event.get("user")
        channel_id = event.get("channel")
        text = event.get("text", "")
        team_id = body.get("team_id", "")
        thread_ts = event.get("thread_ts")
        is_direct_message = channel_id.startswith("D")
        bot_id = body.get("authorizations", [{}])[0].get("user_id", "")
        bot_mentioned = f"<@{bot_id}>" in text if bot_id else False

        logging.info(
            f"Message event details: user_id={user_id}, channel_id={channel_id}, "
            f"team_id={team_id}, text={text}, is_direct_message={is_direct_message}, "
            f"bot_mentioned={bot_mentioned}, thread_ts={thread_ts}"
        )
        logging.info(
            f"Extraction complete in {time.time() - process_start_time:.2f} seconds"
        )

        validation_start_time = time.time()
        if not is_direct_message and not bot_mentioned:
            logging.info(
                "Message is not a direct message and bot is not mentioned. Ignoring."
            )
            return
        logging.info(
            f"Validation complete in {time.time() - validation_start_time:.2f} seconds"
        )

        token_retrieval_start_time = time.time()
        # Retrieve bot token
        token_obj = SlackToken.read(session, team_id)
        if not token_obj:
            logging.error(f"No token found for team {team_id}")
            return

        token = token_obj.bot_access_token
        platform_args = {"slack_token": token, "user_id": user_id}
        helper = SlackHelper.from_token(
            token=token, user_id=user_id, redis=redis.Redis.from_url(REDIS_URL)
        )

        logging.info(
            f"Token retrieval complete in {time.time() - token_retrieval_start_time:.2f} seconds"
        )
        message_processing_start_time = time.time()
        logging.info(
            f"Message from user {user_id} in channel {channel_id} on team {team_id}: {text}"
        )

        if user_id and "bot_id" not in event and text.strip() and team_id:
            # Fetch chat history
            try:
                chat_history_start_time = time.time()
                logging.info("Fetching chat history")
                history = helper.get_chat_history(channel_id, 10, thread_ts=thread_ts)
                logging.info(
                    f"Chat history retrieval completed in {time.time() - chat_history_start_time:.2f} seconds"
                )
                logging.info(f"Chat history retrieved: {len(history)}")
                if not history:
                    history = []

                user_handling_start_time = time.time()
                logging.info("Retrieving user from storage")
                user = User.get_user(session, "slack", team_id, user_id)
                if not user:
                    logging.info(
                        "User not found. Creating new user entry in Firestore storage"
                    )
                    user = User(
                        app_team_id=team_id, app_user_id=user_id, app_name="slack"
                    ).upsert_user(session)

                logging.info(
                    f"User handling completed in {time.time() - user_handling_start_time:.2f} seconds"
                )

                tools_config_start_time = time.time()
                # Setup tools and AI Agent configuration
                tools_dict = {
                    ToolName.WEB_SEARCH: {"proxy": os.getenv("SEARCH_PROXY")},
                    ToolName.REPORT_GENERATOR: dict(
                        llm_conf=LLMConfig(
                            model_provider="openai",
                            model="openrouter/quasar-alpha",
                            llm_kwargs={
                                "api_key": os.getenv("OPENROUTER_API_KEY"),
                                "base_url": "https://openrouter.ai/api/v1",
                            },
                        ),
                        storage_prefix=f"slack/{user.app_team_id}/{user.app_user_id}/",
                    ),
                    ToolName.GOOGLE_MEETS: {},
                    ToolName.GOOGLE_OAUTH: {},
                    ToolName.JIRA: {},
                }
                logging.info(f"Tools configuration set up: {tools_dict}")
                logging.info(
                    f"Tools configuration completed in {time.time() - tools_config_start_time:.2f} seconds"
                )

                task_execution_start_time = time.time()
                # Perform task asynchronously
                logging.info("Starting task execution")
                perform_task.apply_async(
                    kwargs=dict(
                        messages=history,
                        worker_config=WorkerConfig(
                            worker_tools_dict=tools_dict,
                            worker_llm_config=LLMConfig(
                                model_provider="openai",
                                model="openrouter/quasar-alpha",
                                llm_kwargs={
                                    "api_key": os.getenv("OPENROUTER_API_KEY"),
                                    "base_url": "https://openrouter.ai/api/v1",
                                },
                            ),
                            worker_additional_info="",
                        ),
                        platform=Platform.SLACK,
                        platform_args=platform_args,
                        channel_id=channel_id,
                        thread_ts=thread_ts,
                    )
                )
                logging.info(
                    f"Task execution triggered successfully in {time.time() - task_execution_start_time:.2f} seconds"
                )

            except SlackApiError as e:
                logging.error(
                    f"Error posting message: {e.response['error']}", exc_info=True
                )

        logging.info(
            f"Message processing completed in {time.time() - message_processing_start_time:.2f} seconds"
        )

    except Exception as e:
        logging.error(
            f"Unexpected error occurred while processing message: {str(e)}",
            exc_info=True,
        )

    finally:
        # Log the total elapsed time
        elapsed_time = time.time() - start_time
        logging.info(
            f"Message event processing completed in {elapsed_time:.2f} seconds"
        )


@app.action(re.compile(r".*_submit$"))
def handle_submit_button(ack, body, logger):
    """Handle form submissions and extract submitted values into a dictionary"""
    ack()
    logging.info(f"Processed form submission with response: {body}")

    user_id = body["user"]["id"]
    team_id = body["user"]["team_id"]
    channel_id = body.get("channel", {}).get("id")
    action_id = body["actions"][0]["action_id"].replace("_submit", "")
    thread_ts = body.get("message", {}).get("thread_ts") or body.get("message", {}).get(
        "ts"
    )
    message_ts = body.get("message", {}).get("ts")
    session = SessionLocal()

    # Get token from storage
    token_obj = SlackToken.read(session, team_id)
    if not token_obj:
        logging.error(f"No token found for team {team_id}")
        return

    # Use bot_access_token for sending messages
    token = token_obj.bot_access_token
    helper = SlackHelper.from_token(
        token=token, user_id=user_id, redis=redis.Redis.from_url(REDIS_URL)
    )

    # Extract the form values from the state object
    form_values = {}
    if "state" in body and "values" in body["state"]:
        state_values = body["state"]["values"]

        # Iterate through each block in the form
        for block_id, block_data in state_values.items():
            # Each block may contain one or more input elements
            for input_id, input_data in block_data.items():
                # Extract the value based on input type
                if "value" in input_data:
                    # For text inputs, selects, etc.
                    form_values[f"{input_id}"] = input_data["value"]

    logging.info(f"Extracted form values: {form_values}")

    try:
        action_data = json.loads(body["actions"][0]["value"])
        metadata = action_data.get("metadata", {})

        logging.info(
            f"Form '{action_id}' submitted by user {user_id} with metadata: {metadata} Data: {action_data}"
        )

        try:
            FORM_EVENT_HANDLERS[action_id](
                session,
                team_id,
                user_id,
                Platform.SLACK,
                metadata=metadata,
                form_values=form_values,
            )
        except Exception as e:
            helper.send_message(
                channel_id or user_id,
                f"Error in form submission: {str(e)}",
                thread_ts=thread_ts,
            )

        # Try to update the original message to disable the form
        if message_ts:
            try:
                # Get the original blocks and modify them to appear disabled
                blocks = body.get("message", {}).get("blocks", [])
                # Modify blocks to make form appear disabled - replace submit button with text
                for block in blocks:
                    if block.get("type") == "actions":
                        # Replace actions block with a context block indicating completion
                        block["type"] = "context"
                        block["elements"] = [
                            {
                                "type": "plain_text",
                                "text": "✅ Form submitted successfully",
                            }
                        ]

                # Use helper.client instead of global client to ensure proper token usage
                helper.client.chat_update(
                    channel=channel_id or user_id,
                    ts=message_ts,
                    blocks=blocks,
                    text="Form submitted successfully",
                )
            except SlackApiError as e:
                logging.error(f"Error updating form message: {e.response['error']}")
                # Send a new message instead if update fails
                helper.send_message(
                    channel_id or user_id,
                    "✅ Form submitted successfully",
                    thread_ts=thread_ts,
                )

    except AssertionError as e:
        logging.error(f"Assertion error: {str(e)}")
        helper.send_message(channel_id or user_id, str(e), thread_ts=thread_ts)
    except Exception as e:
        logging.error(f"Failed to parse action data from button value: {str(e)}")
        error_message = (
            "There was an issue processing your form submission. Please try again."
        )
        helper.send_message(channel_id or user_id, error_message, thread_ts=thread_ts)


def entry_point():
    """Main function with additional error handling"""
    try:
        # Verify environment variables
        required_env_vars = ["SLACK_APP_TOKEN"]
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
