from datetime import datetime
from typing import Optional, TypedDict
from langchain.chat_models.base import BaseChatModel
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import Tool
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LLMConfig(TypedDict):
    model: str

class WorkerConfig(TypedDict):
    worker_tools_dict: dict
    worker_llm_config: LLMConfig
    worker_additional_info: str = ""
    
    
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

Note: Format any URLs using Slack markdown by enclosing the URL in angle brackets like this: <https://example.com|Click here>. This will render them as clickable hyperlinks in Slack.

Additional Notes:
{day_info}
{self.additional_info}
All dates are in UTC. The tools also expect UTC.
Avoid mentioning technical information like IDs. Use simple language, so simple that even a child understands (important).
Avoid giving raw information. Try to properly format it so it's readable.
Be as useful as possible. Use your tools to the fullest extent to make yourself useful.
"""

    def chat(
        self,
        message: str,
        tools: list[Tool],
    ) -> str:

        agent = create_react_agent(model=self.llm, tools=tools + self.tools, debug=True)
        response: str = agent.invoke(
            {
                "messages": [
                    {"role": "system", "content": self.make_system_prompt()},
                    {"role": "user", "content": message},
                ]
            }
        )["messages"][-1].content
        return response
