from datetime import datetime
from typing import Callable, Optional
from langchain.schema import SystemMessage, HumanMessage
from langchain.chat_models.base import BaseChatModel
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import Tool, tool
from pydantic import BaseModel

import uuid
import time
import threading
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkerAIAgent:
    def __init__(
        self,
        llm: BaseChatModel,
        tools: Optional[list[Tool]] = None,
        additional_info: str = "",
    ) -> None:
        self.llm = llm
        self.tools = tools or []
        self.additional_info = additional_info

    def make_system_prompt(self) -> str:
        day_info = (
            f"Today is {datetime.utcnow().strftime('%A, %B %d, %Y %I:%M %p UTC')}"
        )
        return f"""You are an AI worker developed to assist slack team members and help with productivity.

When you respond to the team members, use phrases like 'I have finished work on the task ....' or 'I have completed this task and i ...' to indicate that you have finished working on a task. 
If you are unable to complete a task, say 'I am unable to complete this task because ...' and explain why you are unable to complete the task.
Additional Notes:
{day_info}
{self.additional_info}
All dates are in UTC the tools also expect utc.
Avoid mentioning techical information like IDs. Use simple language, so simple that even a child understands (important)
Avoid giving raw information. Try to properly format it so its readable.
Be as useful as possible use your tools to full extent to make yourself useful.
"""

    def chat(
        self,
        message: str,
        tools: list[Tool],
        send_message_callback: Callable[[str], None] = None,
    ) -> None:

        agent = create_react_agent(
            model=self.llm,
            tools=tools + self.tools,
            debug=True
        )
        response: str = agent.invoke(
            {
                "messages": [
                    {"role": "system", "content": self.make_system_prompt()},
                    {"role": "user", "content": message},
                ]
            }
        )["messages"][-1].content
        send_message_callback(response)


class OrchestratorAgent:
    def __init__(
        self,
        llm: BaseChatModel,
        worker_tools: list[Tool],
        worker_llm: BaseChatModel,
        disable_checker: bool = False,
        worker_message_callback: Callable[[str], None] = print,
        additional_info: str = "",
        worker_additional_info: str = "",
    ):
        self.disable_checker = disable_checker
        self.llm = llm
        self.worker_tools = worker_tools
        self.additional_info = additional_info
        self.worker_additonal_info = worker_additional_info
        self.worker_llm = worker_llm
        self.worker_message_callback = worker_message_callback

    def make_system_prompt(self) -> str:
        day_info = (
            f"Today is {datetime.utcnow().strftime('%A, %B %d, %Y %I:%M %p UTC')}"
        )
        return f"""You are SlackAI, an AI developed to assist Slack team members and enhance productivity.
Use concise phrases like 'I have started work on XYZ', 'I am still working on task XYZ', or 'I have finished task XYZ' when updating team members.
Be vigilant and attentive to all channel and group messages, but primarily respond when directly addressed or when your input can offer clear value.
Note that conversations might be internal; offer help if it seems beneficial or requested.
You can use your tools to perform tasks; they are capable of handling a wide range of activities.

Consider confirming significant actions, but exercise judgment based on the context and task urgency.
Additional Notes:
{day_info}
{self.additional_info}
All dates are in UTC, and tools also expect UTC.
Refrain from mentioning technical information like IDs. Maintain simple language that even a child can understand (essential).

Tools you can use:
{self.worker_tools}
"""

    def run(self, conversation: list[str]) -> str | None:
        convo_string = "\n".join(conversation)

        if not self.disable_checker:

            class Output(BaseModel):
                reply_to_team: bool
                reason_to_reply: str

            checker_llm = self.llm.with_structured_output(Output)
            output = checker_llm.invoke(
                [
                    SystemMessage(
                        content="""You are to decide whether to reply to the team based on the conversation.
    Only reply to the team if the conversation is directed at you or you have tools that you can use to help the team.
    Dont be spammy, only reply if you have something useful to say. 
    If you are unsure, dont reply.
    Look at the last few messages only.
    """
                    ),
                    HumanMessage(
                        content=f"""Conversation: {convo_string}
    Available tools: {self.worker_tools}
    """
                    ),
                ]
            )

            print(output)
            if not output.reply_to_team:
                return None

        agent = create_react_agent(
            model=self.llm.with_config(config={"tool_choice" : "required"}),
            tools=self.make_tools(),
        )
        response: str = agent.invoke(
            {
                "messages": [
                    {"role": "system", "content": self.make_system_prompt()},
                    {
                        "role": "user",
                        "content": f"Conversation between team:\n {convo_string}",
                    },
                ]
            }
        )["messages"][-1].content

        return response


    def make_tools(self) -> list[Tool]:
        logger.info("Initializing WorkerAIAgent with provided LLM and tools")
        worker = WorkerAIAgent(
            self.worker_llm, self.worker_tools, self.worker_additonal_info
        )

        @tool
        def use_tool(
            task_name: str, task_detail: str, user_confirmed: bool = False
        ) -> str:
            "Used to perform any task, You must provide in long detail description on what needs to be done. Also pass in if user has confirmed or not"
            
            logger.info("use_tool called with task_name: %s, user_confirmed: %s Task Detail: %s", task_name, user_confirmed, task_detail)
            if not user_confirmed:
                logger.warning("User confirmation required for task: %s", task_name)
                return "User confirmation required, ask confirmation and retry if user already confirmed pass user_Confirmed true"

            task_id = str(uuid.uuid4())
            logger.info("Generated task ID: %s for task: %s", task_id, task_name)

            def perform_task():
                logger.info("Starting task execution for task: %s", task_name)
                time.sleep(4)
                logger.info("Task Name: %s\nTask Details: %s", task_name, task_detail)
                worker.chat(
                    f"Task name: {task_name} Task Detail: {task_detail}",
                    tools=[],
                    send_message_callback=self.worker_message_callback,
                )
                logger.info("Task execution completed for task: %s", task_name)

            task_thread = threading.Thread(target=perform_task)
            task_thread.start()
            logger.info("Task in progress for task: %s. You will be notified when it is complete.", task_name)
            return f"Task in progress.... You will be notified when it is complete."

        return [use_tool]