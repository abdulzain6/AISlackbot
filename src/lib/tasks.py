import os
from langgraph.errors import GraphBubbleUp
from ..lib.tools import get_all_tools
from ..lib.platforms import platform_helper_factory, Platform
from .agents.worker import AIAgent, WorkerConfig
from celery import Celery
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage
from datetime import datetime
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
app = Celery(
    "tasks", broker=f"{os.getenv("REDIS_URL")}/0", backend=f"{os.getenv("REDIS_URL")}/1"
)
app.conf.update(
    task_serializer="pickle", result_serializer="pickle", accept_content=["pickle"]
)


@app.task(bind=True)
def perform_task(
    self,
    messages: list[BaseMessage],
    worker_config: WorkerConfig,
    platform: Platform,
    platform_args: dict,
    channel_id: str,
    thread_ts: str = None,
):
    start_time = datetime.now()
    logger.info(f"Task started at: {start_time}")

    step_time_start = datetime.now()
    platform_helper = platform_helper_factory(platform=platform, args=platform_args)
    step_time_end = datetime.now()
    logger.debug(
        f"Initialized platform helper successfully. Time taken: {step_time_end - step_time_start}"
    )

    step_time_start = datetime.now()
    tools = get_all_tools(
        worker_config["worker_tools_dict"], platform, platform_args=platform_args
    )
    step_time_end = datetime.now()
    logger.debug(f"Fetched tools successfully. Time taken: {step_time_end - step_time_start}")

    step_time_start = datetime.now()
    llm = worker_config["worker_llm_config"].to_llm()
    step_time_end = datetime.now()
    logger.debug(f"Initialized LLM successfully. Time taken: {step_time_end - step_time_start}")

    step_time_start = datetime.now()
    addtional_info = worker_config["worker_additional_info"]
    agent = AIAgent(
        tools=tools,
        llm=llm,
        additional_info=addtional_info,
    )
    step_time_end = datetime.now()
    logger.debug(f"Initialized AI Agent successfully. Time taken: {step_time_end - step_time_start}")

    @tool
    def send_starter_message(message: str):
        "Used to send message before starting the task."
        step_time_start = datetime.now()
        logger.debug(f"Sending starter message: {message}")
        platform_helper.send_message(
            channel_id=channel_id,
            thread_ts=thread_ts,
            message=message,
        )
        step_time_end = datetime.now()
        logger.debug(
            f"Starter message sent successfully. Time taken: {step_time_end - step_time_start}"
        )

    try:
        step_time_start = datetime.now()
        logger.info("Attempting to process the agent's chat workflow.")
        output = agent.chat(tools=[send_starter_message], messages=messages)
        logger.info("Agent chat completed successfully.")
        step_time_end = datetime.now()
        logger.debug(f"Agent chat workflow completed. Time taken: {step_time_end - step_time_start}")

        step_time_start = datetime.now()
        logger.debug(f"Sending output message: {output}")
        platform_helper.send_message(
            channel_id=channel_id,
            thread_ts=thread_ts,
            message=output,
        )
        step_time_end = datetime.now()
        logger.info(
            f"Output message sent to platform successfully. Time taken: {step_time_end - step_time_start}"
        )
    except GraphBubbleUp as e:
        logger.error(f"GraphBubbleUp exception occurred: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    finally:
        end_time = datetime.now()
        elapsed_time = end_time - start_time
        logger.info(f"Task ended at: {end_time}. Total execution time: {elapsed_time}.")