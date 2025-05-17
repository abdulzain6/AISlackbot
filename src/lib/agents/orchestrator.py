import base64
import uuid
from io import BytesIO
from datetime import datetime
from typing import Callable, List
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session
from langchain.chat_models.base import BaseChatModel
from langchain_core.messages import BaseMessage, trim_messages, HumanMessage
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import BaseTool, tool
from PIL import Image


from ...lib.platforms.platform_helper import PlatformHelper
from ...database.ai_tasks import AgentTask, TaskStatus
from ...lib.tools import ToolName, get_all_tools, tool_name_to_cls


class Orchestrator:
    """
    Orchestrator class responsible for coordinating worker agents.
    It generates a system prompt describing available tools, the current time,
    and behavior guidelines for task execution.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        worker_tools: dict[ToolName, dict],
        session: Session,
        platform_helper: PlatformHelper,
        send_message_callable: Callable[[str], None],
        orchestrator_additional_info: str,
        uploaded_images: list[bytes],
    ) -> None:
        """
        :param llm: An instance of a LangChain-compatible chat model.
        :param worker_tools: Mapping of ToolName to their configurations.
        """
        self.llm = llm
        self.worker_tools = worker_tools
        self.session = session
        self.platform_helper = platform_helper
        self.send_message_callable = send_message_callable
        self.orchestrator_additional_info = orchestrator_additional_info
        self.image_content = self.process_images(images=uploaded_images)

    def process_images(self, images: list[bytes]):
        image_content = []
        for image in images:
            img = Image.open(BytesIO(image))
            # Convert to RGB (for formats with alpha)
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            # Save to JPEG buffer
            buf = BytesIO()
            img.save(buf, format="JPEG")
            jpeg_bytes = buf.getvalue()
            # Base64 for LLM prompt
            base64_image = base64.b64encode(jpeg_bytes).decode("utf-8")
            image_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                }
            )
        return image_content

    def _build_tool_message(self) -> str:
        """
        Constructs a list of toolkits and their descriptions.
        """
        lines = []
        for tool_name in self.worker_tools.keys():
            tool_cls = tool_name_to_cls[tool_name][0]
            lines.append(f"- {tool_name.value}: {tool_cls.DESCRIPTION}")
        return "\n".join(lines)

    def _build_system_message(self, tool_message: str) -> str:
        """
        Constructs the full system prompt, including behavior guidelines,
        available toolkits, and current UTC time.
        """
        utc_now = datetime.utcnow().strftime("%A, %B %d, %Y %I:%M %p UTC")
        return (
            "You are SlackAI, an intelligent assistant operating inside Slack.\n\n"
            "Your Role:\n"
            "- Assist Slack users efficiently and professionally.\n"
            "- Delegate tasks to worker agents when necessary.\n"
            "- Create new agents only if existing tools or agents are insufficient.\n"
            "- Assign toolkits appropriately to maximize worker performance.\n"
            "- Communicate with users as if you are doing the work yourself.\n"
            "- Be polite, helpful, and focus on driving productivity.\n\n"
            "Communication Style:\n"
            "- Use first-person language (e.g., 'I have started working on...').\n"
            "- Sound professional but approachable.\n"
            "- Keep users updated on task progress naturally.\n\n"
            "Available Toolkits:\n"
            "------------------\n"
            f"{tool_message}\n"
            "------------------\n\n"
            f"Current UTC time: {utc_now}\n"
            f"Important: {self.orchestrator_additional_info}\n"
            "User must not know of the agent, the must know you are doing everything\n"
            "Only spawn worker if you are fully sure.\n"
            "Remember that you do not have access to the knowledgebase you can only access chat files. For all knwledgebase related tasks make a worker.\n"
            "Always check if a task is already running if it is, confirm with user if they want to run again."
        )

    def get_system_prompt(self) -> str:
        """
        Public API: Returns the complete system prompt ready to be sent to the LLM.
        """
        tool_msg = self._build_tool_message()
        return self._build_system_message(tool_msg)

    def get_running_tasks(self, include_complete: bool = True) -> list[AgentTask]:
        return AgentTask.list_by_team_and_platform(
            self.session,
            self.platform_helper.team_id,
            self.platform_helper.platform_name,
            include_complete=include_complete,
        )

    def spawn_worker(
        self,
        tool_names: list[str],
        ai_name: str,
        instructions: str,
        message: str,
    ) -> str:
        tools = {}
        for tool in tool_names:
            try:
                enum_key = ToolName(tool)
            except ValueError as e:
                raise ValueError(f"Unknown tool name: {tool}") from e
            tools[enum_key] = self.worker_tools[enum_key]

        agent = create_react_agent(
            model=self.llm,
            tools=get_all_tools(
                toolnames_to_args=tools, platform_helper=self.platform_helper
            ),
            debug=True,
        )
        utc_now = datetime.utcnow().strftime("%A, %B %d, %Y %I:%M %p UTC")
        response = agent.invoke(
            {
                "messages": [
                    {
                        "role": "system",
                        "content": f"""
                    You are {ai_name}
                    {instructions}
                    Today is {utc_now}
                    """,
                    },
                    {"role": "human", "content": message},
                    *self.image_content
                ]
            }
        )["messages"]
        return response[-1].content

    def _run_worker(
        self,
        task_id: str,
        tool_names: List[str],
        ai_name: str,
        instructions: str,
        message: str,
    ) -> str:
        """
        Target function for background thread:
        - Calls spawn_worker
        - On success: marks task COMPLETE
        - On exception: marks task FAILED
        """
        try:
            result = self.spawn_worker(
                tool_names=tool_names,
                ai_name=ai_name,
                instructions=instructions,
                message=message,
            )
            # Update the task status to COMPLETE
            AgentTask.update(
                session=self.session,
                task_id=task_id,
                status=TaskStatus.COMPLETE,
                description=f"{AgentTask.read(self.session, task_id).description}\n\nResult:\n{result}",
            )
            return result
        except Exception as e:
            # Mark the task as FAILED and log the error message
            AgentTask.update(
                session=self.session,
                task_id=task_id,
                status=TaskStatus.FAILED,
                description=f"{AgentTask.read(self.session, task_id).description}\n\nError:\n{e}",
            )
            return f"Task failed with error: {e}"

    def make_tools(self) -> list[BaseTool]:
        @tool
        def get_running_tasks(include_complete: bool = False) -> str:
            """
            Used to get the tasks currently running.
            If include_complete=True, includes completed tasks.
            Returns a Markdown-formatted table of tasks.
            """
            tasks = self.get_running_tasks(include_complete=include_complete)

            if not tasks:
                return "No tasks found."

            # Build Markdown table header
            header = "| ID | Task Name | Status | Assigned To | Created At |\n"
            header += "|----|-----------|--------|-------------|------------|\n"

            # Build each row
            rows = []
            for t in tasks:
                rows.append(
                    f"| {t.id} "
                    f"| {t.task_name} "
                    f"| {t.status.value} "
                    f"| {t.assigned_to} "
                    f"| {t.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')} |"
                )

            return header + "\n".join(rows)

        @tool
        def spawn_ai_worker(
            tool_names: List[str],
            task_name: str,
            ai_name: str,
            instructions: str,
            message: str,
            message_for_the_user: str,
        ) -> str:
            """
            Spawn a background AI worker to handle a task.

            Args:
              - tool_names: List of tool-name strings (must match ToolName enum)
              - ai_name:    The AI agent’s name/role
              - task_name name of the task
              - instructions: System-level instructions for the agent
              - message:      The initial human message
              - message_for_the_user: str: A message for the user that you have started work on the task. Do not ask questions here.

            Returns:
              A confirmation string. The actual work runs in the background,
              and the task record in the database will be updated when done.
            """
            # 1) Persist a new task in the DB as IN_PROGRESS
            if not message_for_the_user:
                raise ValueError(
                    "A message must be sent to the user saying you starting to work before spawning worker."
                )

            self.platform_helper.send_message(message_for_the_user)  # type: ignore

            task = AgentTask.create(
                session=self.session,
                id=str(uuid.uuid4()),
                team_id=self.platform_helper.team_id,
                platform_name=self.platform_helper.platform_name,
                status=TaskStatus.IN_PROGRESS,
                task_name=task_name,
                description=instructions,
                assigned_to=ai_name,
                assignee_instructions=message,
            )

            # 2) Launch a background thread to run the actual work
            return self._run_worker(
                task_id=task.id,
                tool_names=tool_names,
                ai_name=ai_name,
                instructions=instructions,
                message=message,
            )

        @tool
        def send_user_message(message: str):
            "Used to send message to the user, Used to provide updates the user (Only use if needed)"
            self.send_message_callable(message)
            return "Message sent"

        @tool
        def list_uploaded_files():
            """List the files uploaded lately by the user. These are file uploads don't need to be in the knowledgebase"""
            user_files = self.platform_helper.get_recent_file_info()
            if not user_files:
                return "No files have been uploaded lately. Note: For knowledegebase files spawn worker"

            return f"{user_files} \nNote: For knowledegebase files spawn worker"

        return [
            get_running_tasks,
            spawn_ai_worker,
            send_user_message,
            list_uploaded_files,
        ]

    def chat(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        agent = create_react_agent(
            model=self.llm,
            tools=self.make_tools(),
            debug=True
        )
        messages = trim_messages(
            messages=messages,
            max_tokens=2000,
            token_counter=ChatOpenAI(model="gpt-4o", api_key="api_lkey"),
        )

        if isinstance(messages[-1], HumanMessage):
            if isinstance(messages[-1].content, str):
                messages[-1].content = [
                    {"type" : "text", "text": messages[-1].content},
                    *self.image_content
                ]
            elif isinstance(messages[-1].content, list):
                messages[-1].content.extend(self.image_content)

        response: str = agent.invoke(
            {
                "messages": [
                    {"role": "system", "content": self.get_system_prompt()},
                    *messages
                ]
            }
        )["messages"]
        return response
