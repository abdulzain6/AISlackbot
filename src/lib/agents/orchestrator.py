from typing import TypedDict
from datetime import datetime
import uuid
from langchain.schema import SystemMessage, HumanMessage
from langchain.chat_models.base import BaseChatModel
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import Tool, tool
from pydantic import BaseModel
from ..platforms import Platform
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



class OrchestratorAgent:
    def __init__(
        self,
        llm: BaseChatModel,
        run_worker_task,
        worker_tools: str,
        disable_checker: bool = False,
        additional_info: str = "",
    ):
        self.disable_checker = disable_checker
        self.llm = llm
        self.additional_info = additional_info
        self.worker_tools = worker_tools
        self.run_worker_task = run_worker_task

    def make_system_prompt(self) -> str:
        day_info = (
            f"Today is {datetime.utcnow().strftime('%A, %B %d, %Y %I:%M %p UTC')}"
        )
        if not self.disable_checker:
            message = "If you think you can help with the task ask something like 'I can help with task XYZ, would you like me to do it?'"
        else:
            message = "The message is directed to you so you should respond to it."

        return f"""You are SlackAI, an AI developed to assist Slack team members and enhance productivity.
Use concise phrases like 'I have started work on XYZ', 'I am still working on task XYZ', or 'I have finished task XYZ' when updating team members.
{message} (Important)
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
                        content=f"""Conversation: {convo_string}
    Available tools: {self.worker_tools}
    """
                    ),
                ]
            )
            logger.info(f"Checker output: {output}")
            if not output.reply_to_team:
                return None

        agent = create_react_agent(
            model=self.llm.with_config(config={"tool_choice": "required"}),
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

        @tool
        def use_tool(task_name: str, task_detail: str) -> str:
            "Used to perform any task, You must provide in long detail description on what needs to be done. Also pass in if user has confirmed or not"
            try:
                logger.info(
                    "use_tool called with task_name: %s, Task Detail: %s",
                    task_name,
                    task_detail,
                )

                task_id = str(uuid.uuid4())
                logger.info("Task ID: %s", task_id)
                result = self.run_worker_task(
                    task_name=task_name,
                    task_detail=task_detail,
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
            
        return [use_tool]
