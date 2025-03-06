from langgraph.errors import GraphBubbleUp
from ..lib.tools import get_all_tools
from ..lib.platforms import platform_helper_factory, Platform
from .agents.worker import AIAgent, WorkerConfig
from celery import Celery
from langchain_core.tools import tool
import logging



logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
app = Celery(
    "tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/1"
)
app.conf.update(
    task_serializer="pickle", result_serializer="pickle", accept_content=["pickle"]
)


@app.task(bind=True)
def perform_task(
    self,
    conversation: list[str],
    worker_config: WorkerConfig,
    platform: Platform,
    platform_args: dict,
    channel_id: str,
    disable_doing_nothing: bool,
    thread_ts: str = None,
):
    platform_helper = platform_helper_factory(platform=platform, args=platform_args)
    tools = get_all_tools(
        worker_config["worker_tools_dict"], platform, platform_args=platform_args
    )
    llm = worker_config["worker_llm_config"].to_llm()
    addtional_info = worker_config["worker_additional_info"]
    if not disable_doing_nothing:
        addtional_info = f"{addtional_info}\n Call no_reply if you cannot add value and people are just chatting between themselves (You dont have to reply to everything unless its directed to you)"

    agent = AIAgent(
        tools=tools,
        llm=llm,
        additional_info=addtional_info,
    )

    @tool
    def update_user_about_task_progress(message: str):
        "Reply to the channel with a message. Only call this for long haul tasks to tell about progress"
        platform_helper.send_message(
            channel_id=channel_id,
            thread_ts=thread_ts,
            message=message,
        )

    @tool
    def no_reply(reason: str):
        "Dont reply user. Takes in why you are not replying."
        print(reason)
        self.app.control.revoke(self.request.id, terminate=True)
        raise GraphBubbleUp()


    tools = [update_user_about_task_progress]
    if not disable_doing_nothing:
        tools.append(no_reply)
    try:
        output = agent.chat(tools=tools, conversation=conversation)
    except GraphBubbleUp:
        return
    platform_helper.send_message(
        channel_id=channel_id, message=output, thread_ts=thread_ts
    )
