from datetime import datetime
from langchain_openai import ChatOpenAI
from ..lib.tools import get_all_tools
from ..lib.platforms import SendMessageConfig, send_message, Platform
from ..database.user_tasks import FirebaseUserTasks, TaskStatus, Task
from ..database.users import User
from .agents.worker import WorkerAIAgent, WorkerConfig
from celery import Celery

import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Celery(
    "tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/1"
)
app.conf.update(
    task_serializer="pickle", result_serializer="pickle", accept_content=["pickle"]
)


@app.task
def perform_task(
    task_name: str,
    task_detail: str,
    task_id: str,
    worker_config: WorkerConfig,
    send_message_config: SendMessageConfig,
    platform: Platform,
    user: User,
):
    time.sleep(4)
    try:
        tools = get_all_tools(worker_config["worker_tools_dict"])
        llm = ChatOpenAI(model=worker_config["worker_llm_config"]["model"])
        addtional_info = worker_config["worker_additional_info"]

        worker_agent = WorkerAIAgent(
            tools=tools, llm=llm, additional_info=addtional_info
        )
        logger.info("Starting task execution for task: %s", task_name)
        logger.info("Task Name: %s\nTask Details: %s", task_name, task_detail)

        FirebaseUserTasks().create_task(
            Task(
                team_id=user.app_team_id,
                task_name=task_name,
                task_detail=task_detail,
                app_name=platform.value.lower(),
                status=TaskStatus.IN_PROGRESS,
                task_id=task_id,
                time_created=datetime.utcnow(),
            )
        )
        output = worker_agent.chat(
            f"Task name: {task_name} Task Detail: {task_detail}",
            tools=[],
        )
        send_message(config=send_message_config, platform=platform, message=output)
        FirebaseUserTasks().update_task_status(
            user.app_team_id, platform.value.lower(), task_id, TaskStatus.COMPLETED
        )
        logger.info("Task execution completed for task: %s", task_name)
    except Exception as e:
        if FirebaseUserTasks().read_task(
            user.app_team_id, platform.value.lower(), task_id
        ):
            FirebaseUserTasks().update_task_status(
                user.app_team_id, platform.value.lower(), task_id, TaskStatus.FAILED
            )
        logger.error("Task execution failed for task: %s due to %s", task_name, e)
