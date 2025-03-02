import json
import logging
import os
import re

from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError
from langchain_openai import ChatOpenAI
from .database.slack_tokens import FirebaseSlackTokenStorage
from .lib.event_handlers import FORM_EVENT_HANDLERS
from .lib.tools.report_generator import LLMConfig
from .lib.agents.worker import WorkerConfig
from .database.users import User, FirestoreUserStorage
from .lib.tools import ToolName
from .lib.platforms.slack import SlackHelper
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

        token = FirebaseSlackTokenStorage().get_token(team_id).bot_access_token
        if not token:
            logging.error(f"No token found for team {team_id}")
            return

        platform_args = {"slack_token": token, "user_id": user_id}
        helper = SlackHelper.from_token(token=token, user_id=user_id)

        logging.info(
            f"Message from user {user_id} in channel {channel_id} team {team_id}: {text}"
        )

        if user_id and "bot_id" not in event and text.strip() and team_id:
            try:

                history = helper.get_chat_history(channel_id, 10, thread_ts=thread_ts)
                user = FirestoreUserStorage().get_user("slack", team_id, user_id)
                if not user:
                    user = User(
                        app_team_id=team_id, app_user_id=user_id, app_name="slack"
                    )
                    FirestoreUserStorage().upsert_user(user)

                # Setup AI Agent
                tools_dict = {
                    ToolName.WEB_SEARCH: {},
                    ToolName.REPORT_GENERATOR: dict(
                        llm_conf=LLMConfig(
                            model_provider="openai", model="gpt-4o-mini", llm_kwargs={}
                        ),
                        storage_prefix=f"slack/{user.app_team_id}/{user.app_user_id}/",
                    ),
                    ToolName.GOOGLE_MEETS: {},
                    ToolName.GOOGLE_OAUTH: {}
                }
                perform_task.apply_async(
                    kwargs=dict(
                        conversation=[
                            f'{message["display_name"]}: {message["message"]}'
                            for message in history
                        ],
                        worker_config=WorkerConfig(
                            worker_tools_dict=tools_dict,
                            worker_llm_config=LLMConfig(
                                model_provider="openai", model="gpt-4o", llm_kwargs={}
                            ),
                            worker_additional_info="",
                        ),
                        platform=Platform.SLACK,
                        platform_args=platform_args,
                        channel_id=channel_id,
                        thread_ts=thread_ts,
                        disable_doing_nothing=is_direct_message or bot_mentioned,
                    )
                )

            except SlackApiError as e:
                logging.error(f"Error posting message: {e.response['error']}")

    except Exception as e:
        logging.error(f"Error processing message: {str(e)}", exc_info=True)


@app.action(re.compile(r".*_submit$"))
def handle_submit_button(ack, body, logger):
    """Handle form submissions and extract submitted values into a dictionary"""
    ack()
    logger.info(f"Processed form submission with response: {body}")

    user_id = body["user"]["id"]
    team_id = body["user"]["team_id"]
    channel_id = body.get("channel", {}).get("id")
    action_id = body["actions"][0]["action_id"].replace("_submit", "")
    thread_ts = body.get("message", {}).get("thread_ts") or body.get("message", {}).get(
        "ts"
    )
    message_ts = body.get("message", {}).get("ts")
    token = FirebaseSlackTokenStorage().get_token(team_id).bot_access_token
    if not token:
        logging.error(f"No token found for team {team_id}")
        return

    helper = SlackHelper.from_token(token=token, user_id=user_id)

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

    logger.info(f"Extracted form values: {form_values}")

    try:
        action_data = json.loads(body["actions"][0]["value"])
        metadata = action_data.get("metadata", {})

        logger.info(
            f"Form '{action_id}' submitted by user {user_id} with metadata: {metadata} Data: {action_data}"
        )

        FORM_EVENT_HANDLERS[action_id](
            team_id, user_id, "slack", metadata=metadata, form_values=form_values
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

                # Update the original message
                client.chat_update(
                    channel=channel_id or user_id,
                    ts=message_ts,
                    blocks=blocks,
                    text="Form submitted successfully",
                )
            except SlackApiError as e:
                logger.error(f"Error updating form message: {e.response['error']}")

    except AssertionError as e:
        logger.error(f"Assertion error: {str(e)}")
        helper.send_message(channel_id or user_id, str(e), thread_ts=thread_ts)
    except Exception as e:
        logger.error(f"Failed to parse action data from button value: {str(e)}")
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
