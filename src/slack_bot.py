import json
import logging
import os
import re
import time
import uuid
import psycopg
import redis

from langchain_postgres import PostgresChatMessageHistory
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError
from langchain_core.messages import HumanMessage
from .lib.tools.image_generator import ImageGeneratorConfig
from .lib.event_handlers import FORM_EVENT_HANDLERS
from .lib.models.llm import LLMConfig
from .database.users import User
from .database.slack_tokens import SlackToken
from .database.engine import SessionLocal
from .lib.tools import ToolName
from .lib.platforms.slack import SlackHelper
from .lib.platforms import Platform
from .lib.tasks import AgentConfig, perform_task
from .globals import app, REDIS_URL


redis_client = redis.Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True
)


@app.event("message")
def handle_message_events(body, say):
    """Handle message events with detailed logging, time tracking, and thread support, including bot mention detection"""
    start_time = time.time()  # Track the start time for execution
    logging.info("Event received: Processing message event")
    logging.debug(f"Event body: {json.dumps(body, indent=2)}")
    session = SessionLocal()

    try:
        event = body.get("event", {})
        user_id = event.get("user")
        channel_id = event.get("channel")
        text = event.get("text", "")
        team_id = body.get("team_id", "")
        thread_ts = event.get("thread_ts")
        message_ts = event.get("ts")
        files = event.get("files", [])
        is_direct_message = channel_id.startswith("D")
        bot_id = body.get("authorizations", [{}])[0].get("user_id", "")
        bot_mentioned = f"<@{bot_id}>" in text if bot_id else False

        logging.info(
            f"Message event details: user_id={user_id}, channel_id={channel_id}, "
            f"team_id={team_id}, text={text}, is_direct_message={is_direct_message}, "
            f"bot_mentioned={bot_mentioned}, thread_ts={thread_ts}"
        )

        token_obj = SlackToken.read(session, team_id)
        if not token_obj:
            logging.info(
                "No token found for the given team_id, unable to proceed with message processing."
            )
            return

        token = token_obj.bot_access_token
        platform_args = {
            "token": token,
            "user_id": user_id,
            "thread_ts": thread_ts,
            "message_ts": message_ts,
            "channel_id": channel_id,
        }
        helper = SlackHelper.from_token(
            token=token, user_id=user_id, redis=redis.Redis.from_url(REDIS_URL)
        )

        # 1) Try cache lookup for user name
        cache_key_name = f"user_name:{user_id}"
        cache_key_email = f"user_email:{user_id}"

        user_name = redis_client.get(cache_key_name)
        email = redis_client.get(cache_key_email)

        # 2) If missing, fetch from Slack API and cache
        if (not user_name or not email) and user_id:
            resp = helper.client.users_info(user=user_id)
            if resp.get("ok"):
                profile = resp.get("user", {}).get("profile", {})
                user_name = (
                    profile.get("display_name") or profile.get("real_name") or user_id
                )
                email = profile.get("email")

                if not user_name:
                    user_name = user_id

                redis_client.set(cache_key_name, user_name, ex=86400)
                if email:
                    redis_client.set(cache_key_email, email, ex=86400)
            else:
                logging.warning(f"users.info failed for {user_id}: {resp.get('error')}")
                user_name = user_id
                email = None

        # 3) Prepend the user’s name to the message text
        email_message = f"({email})" if email else ""
        text = f"{user_name} {email_message}: {text}"

        if not token_obj:
            logging.error(f"No token found for team {team_id}")
            return

        if not is_direct_message and not bot_mentioned:
            sync_connection = psycopg.connect(
                os.getenv("DATABASE_URL", "").replace("+psycopg", "")
            )
            chat_history = PostgresChatMessageHistory(
                "chat_history",
                str(
                    uuid.uuid5(
                        uuid.NAMESPACE_DNS,
                        f"{channel_id}_{thread_ts}_{Platform.SLACK.value}_{team_id}",
                    )
                ),
                sync_connection=sync_connection,
            )
            chat_history.create_tables(sync_connection, "chat_history")
            chat_history.add_message(HumanMessage(content=text))

            if files:
                helper.send_message(
                    "📂 I see you've uploaded some files! Would you like me to add them to your knowledgebase? 🤔 Please @ me if you want me to do that. This will allow me to answer questions based on the content of those files.",
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                )
            else:
                logging.info(
                    "Message is not a direct message and bot is not mentioned. Ignoring."
                )
            return

        if user_id and "bot_id" not in event and text.strip() and team_id:
            try:
                logging.info("Retrieving user from storage")
                user = User.get_user(session, "slack", team_id, user_id)
                if not user:
                    user = User(
                        app_team_id=team_id, app_user_id=user_id, app_name="slack"
                    ).upsert_user(session)

                files_message = (
                    f"""
                The user uploaded some files with this message.
                File Names: {[file["name"] for file in files]}.
                Note: There may be more files uploaded before this message, use you tools if you need to see them.
                Respond accordingly, ask them if you can assist them with the files (important)
                """
                    if files
                    else ""
                )

                tools_dict = {
                    ToolName.WEB_SEARCH: {"proxy": os.getenv("SEARCH_PROXY")},
                    ToolName.REPORT_GENERATOR: dict(
                        llm_conf=LLMConfig(
                            model_provider="openai",
                            model="gpt-4.1-mini-2025-04-14",
                            llm_kwargs={"api_key": os.getenv("OPENAI_API_KEY", "")},
                        ),
                        storage_prefix=f"slack/{user.app_team_id}/{user.app_user_id}/",
                    ),
                    ToolName.GOOGLE_MEETS: {},
                    ToolName.GOOGLE_OAUTH: {},
                    ToolName.JIRA: {},
                    ToolName.UML_DIAGRAM_MAKER: {},
                    ToolName.PRESENTATION_MAKER: dict(
                        llm_config=LLMConfig(
                            model_provider="openai",
                            model="gpt-4.1-mini-2025-04-14",
                            llm_kwargs={
                                "api_key": os.getenv("OPENAI_API_KEY", ""),
                            },
                        ),
                        image_generator_config=ImageGeneratorConfig(
                            replicate_api_key=os.getenv("REPLICATE_API_KEY", "")
                        ),
                    ),
                    ToolName.IMAGE_GENERATOR: dict(
                        replicate_api_key=os.getenv("REPLICATE_API_KEY")
                    ),
                    ToolName.KNOWLEDGEBASE_TOOLKIT: dict(
                        llm_conf=LLMConfig(
                            model_provider="openai",
                            model="gpt-4.1-mini-2025-04-14",
                            llm_kwargs={
                                "api_key": os.getenv("OPENAI_API_KEY", ""),
                            },
                        ),
                    ),
                }

                uploaded_images: list[bytes] = []
                for file in files:
                    if re.search(r'\.(jpg|jpeg|png|webp)$', file["name"], re.IGNORECASE):
                        uploaded_images.append(helper.get_file_bytes(file["id"]))
              
                perform_task.apply_async(  # type: ignore
                    kwargs=dict(
                        uploaded_images=uploaded_images,
                        message=HumanMessage(content=text),
                        worker_config=AgentConfig(
                            worker_tools_dict=tools_dict,
                            llm_config=LLMConfig(
                                model_provider="openai",
                                model="gpt-4.1-mini-2025-04-14",
                                llm_kwargs={"api_key": os.getenv("OPENAI_API_KEY", "")},
                            ),
                            orchestrator_additional_info=files_message,
                        ),
                        platform=Platform.SLACK,
                        platform_args=platform_args,
                        channel_id=channel_id,
                        thread_ts=thread_ts,
                    )
                )
            except SlackApiError as e:
                logging.error(
                    f"Error posting message: {e.response['error']}", exc_info=True
                )

    except Exception as e:
        logging.error(
            f"Unexpected error occurred while processing message: {str(e)}",
            exc_info=True,
        )

    finally:
        elapsed_time = time.time() - start_time
        logging.info(
            f"Message event processing completed in {elapsed_time:.2f} seconds"
        )


@app.action(re.compile(r".*_submit$"))
def handle_form_submission(ack, body, logger):
    """Handle form submissions and extract submitted values into a dictionary"""
    ack()
    logging.debug(f"Processed form submission with response: {body}")

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
    # print("Gmail Job scheduled!")
    entry_point()
