from typing import Callable
from datetime import datetime
from langchain.schema import SystemMessage, HumanMessage
from langchain.chat_models.base import BaseChatModel
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import Tool, tool
from pydantic import BaseModel
import logging
import uuid


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrchestratorAgent:
    def __init__(
        self,
        llm: BaseChatModel,
        run_worker_task: Callable[[str], None],
        worker_tools: list[Tool],
        orchestrator_tools: list[Tool],
        disable_checker: bool = False,
        additional_info: str = "",
    ):
        self.disable_checker = disable_checker
        self.llm = llm
        self.additional_info = additional_info
        self.worker_tools = worker_tools
        self.run_worker_task = run_worker_task
        self.orchestrator_tools = orchestrator_tools

        self.task_executed = False
        self.last_task_executed = None

    def make_system_prompt(self, is_directed_to_ai: bool) -> str:
        day_info = (
            f"Today is {datetime.utcnow().strftime('%A, %B %d, %Y %I:%M %p UTC')}"
        )
        if not is_directed_to_ai:
            message = "The message is not directed to you, If you think you can help with the task ask something like 'I can help with task XYZ, would you like me to do it?'"
        else:
            message = "The message is directed to you so act accordingly, execute a task if needed or respond to the message."

        return f"""You are SlackAI, an AI developed to assist Slack team members and enhance productivity.
Be vigilant and attentive to all channel and group messages, but primarily respond when directly addressed or when your input can offer clear value.
Note that conversations might be internal; offer help if it seems beneficial or requested.
Consider confirming significant actions, but exercise judgment based on the context and task urgency.
Refrain from mentioning technical information like IDs. 
Maintain simple language that even a child can understand (essential).
Look at what you have already done and avoid making duplicate tasks, if you think the task is duplicate, ask the user to confirm.
If you think you cannot do the task simply call execute_user_request.

Additional Notes:
=================
{day_info}
{self.additional_info}
All dates are in UTC.
Note: Format any URLs using Slack markdown by enclosing the URL in angle brackets like this: <https://example.com|Click here>. This will render them as clickable hyperlinks in Slack.
=================

{message} (Important)
"""

    def run(self, conversation: list[str]) -> str | None:
        convo_string = "\n".join(conversation)

        if not self.disable_checker:
            class Output(BaseModel):
                reply_to_team: bool
                is_directed_to_ai: bool
                reason_to_reply: str

            checker_llm = self.llm.with_structured_output(Output)
            output: Output = checker_llm.invoke(
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
                        content=f"""Conversation: 
============
{convo_string}
============
Available tools: {self.worker_tools}
    """
                    ),
                ]
            )
            logger.info(f"Checker output: {output}")
            if not output.reply_to_team:
                return None
            
            directed_to_ai = output.is_directed_to_ai
        else:
            directed_to_ai = True

        agent = create_react_agent(
            model=self.llm.with_config(config={"tool_choice": "required"}),
            tools=[*self.make_tools(), *self.orchestrator_tools],
        )
        response: str = agent.invoke(
            {
                "messages": [
                    {"role": "system", "content": self.make_system_prompt(directed_to_ai)},
                    {
                        "role": "user",
                        "content": f"""
Reminder: You must call execute_user_request to execute tasks
Only call execute_user_request once put the whole task in as is, no need to split it into multiple calls
Make sure to not make duplicate tasks.  
If you think you cannot do the task simply call execute_user_request.
Conversation between team:
==================          
{convo_string}
==================
AI:""",
                    },
                ]
            }
        )["messages"][-1].content

        return response

    def make_tools(self) -> list[Tool]:
        @tool
        def execute_user_request(task_name: str, complete_task_detail: str) -> str:
            """
            Used to execute a user's requeest 
            You must provide in long detail description on what needs to be done.
            This can be called only once, so put in the task completely, use 'and' if needed.
            """

            try:
                if not self.task_executed:
                    self.task_executed = True
                else:
                    return f"You can only execute one task at a time. Already running: {self.last_task_executed}"
                
                logger.info(
                    "execute_user_request called with task_name: %s, Task Detail: %s",
                    task_name,
                    complete_task_detail,
                )

                task_id = str(uuid.uuid4())
                logger.info("Task ID: %s", task_id)
                result = self.run_worker_task(
                    task_name=task_name,
                    task_detail=complete_task_detail,
                    task_id=task_id,
                )
                logger.info(
                    "Task in progress for task: %s. You will be notified when it is complete.",
                    task_name,
                )
                return f"Task in progress.... You will be notified when it is complete."
            except Exception as e:
                logger.error("Error in use_tool: %s", e)
                return f"Error: {e}"

        return [execute_user_request]
