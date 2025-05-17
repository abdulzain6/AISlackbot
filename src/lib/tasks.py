import os
import traceback
import logging
from typing import TypedDict
import uuid
import psycopg

from ..lib.models.llm import LLMConfig
from ..database.engine import SessionLocal
from ..lib.agents.orchestrator import Orchestrator
from ..lib.platforms import platform_helper_factory, Platform

from celery import Celery
from langgraph.errors import GraphBubbleUp
from langchain_core.messages import HumanMessage, BaseMessage, SystemMessage
from langchain_postgres import PostgresChatMessageHistory
from datetime import datetime
from redis import Redis


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
app = Celery(
    "tasks", broker=f"{os.getenv('REDIS_URL')}/0", backend=f"{os.getenv('REDIS_URL')}/1"
)
app.conf.update(
    task_serializer="pickle", result_serializer="pickle", accept_content=["pickle"]
)
redis_client = Redis.from_url(os.getenv("REDIS_URL", ""))


class AgentConfig(TypedDict):
    worker_tools_dict: dict
    llm_config: LLMConfig
    orchestrator_additional_info: str



@app.task(bind=True)
def perform_task(
    self,
    uploaded_images: list[bytes],
    message: HumanMessage,
    worker_config: AgentConfig,
    platform: Platform,
    platform_args: dict,
    channel_id: str,
    thread_ts: str | None = None,
):
    sync_connection = psycopg.connect(os.getenv("DATABASE_URL", "").replace("+psycopg", ""))
    
    start_time = datetime.now()
    logger.info(f"Task started at: {start_time}")
    platform_helper = platform_helper_factory(platform=platform, args=platform_args)

    chat_history = PostgresChatMessageHistory(
        "chat_history",
        str(uuid.uuid5(
            uuid.NAMESPACE_DNS,
            f"{channel_id}_{thread_ts}_{platform.value}_{platform_helper.team_id}",
        )),
        sync_connection=sync_connection,
    )
    chat_history.create_tables(sync_connection, "chat_history")
    llm = worker_config["llm_config"].to_llm()

    def send_message_callable(message: str):
        "Used to send message before starting the task."
        logger.debug(f"Sending starter message: {message}")
        platform_helper.send_message(
            channel_id=channel_id,
            thread_ts=thread_ts,
            message=message,
        )

    try:
        agent = Orchestrator(
            llm=llm,
            worker_tools=worker_config["worker_tools_dict"],
            platform_helper=platform_helper,
            send_message_callable=send_message_callable,
            session=SessionLocal(),
            orchestrator_additional_info=worker_config["orchestrator_additional_info"],
            uploaded_images=uploaded_images
        )

        messages_in: list[BaseMessage] = chat_history.get_messages() + [message]
        messages_in_ids = [message.id for message in messages_in]
        messages_out = agent.chat(messages=messages_in)

        chat_history.add_messages(
            [
                message
                for message in messages_out
                if message.id not in messages_in_ids
                and not isinstance(message, SystemMessage)
            ]
        )

        output = messages_out[-1].content
        platform_helper.send_message(
            channel_id=channel_id,
            thread_ts=thread_ts,
            message=output,
        )

    except GraphBubbleUp as e:
        logger.error(f"GraphBubbleUp exception occurred: {e}")
    except Exception as e:
        traceback.print_exc()
        logger.error(f"An unexpected error occurred: {e}")
    finally:
        end_time = datetime.now()
        elapsed_time = end_time - start_time
        logger.info(
            f"Task ended at: {end_time}. Total execution time: {elapsed_time}."
        )
