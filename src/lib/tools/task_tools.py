from langchain_core.tools import Tool, tool

from ...lib.platforms import Platform
from .tool_maker import ToolMaker, ToolConfig
from ...database.user_tasks import FirebaseUserTasks, TaskStatus
from celery import current_app
from pydantic import BaseModel


class TasksConfig(BaseModel):
    team_id: str
    user_tasks: FirebaseUserTasks = None
    platform: Platform

    class Config:
        arbitrary_types_allowed = True


class TaskTools(ToolMaker):
    def __init__(self, tool_config: TasksConfig):
        if not tool_config.user_tasks:
            tool_config.user_tasks = FirebaseUserTasks()

        self.user_tasks = tool_config.user_tasks
        self.team_id = tool_config.team_id
        self.platform = tool_config.platform

    def create_ai_tools(self) -> list[Tool]:
        @tool
        def get_latest_tasks(number_of_tasks: int = 10):
            "Use this to get all tasks for the team."
            tasks = self.user_tasks.get_latest_tasks_for_team(
                self.team_id, self.platform.value.lower(), number_of_tasks
            )
            if not tasks:
                return "No tasks found."
            return "\n".join(
                [
                    f"Task Name: {task.task_name}, Task Detail: {task.task_detail}, Status: {task.status}"
                    for task in tasks
                ]
            )

        @tool
        def cancel_task(task_id: str):
            "Use this to cancel a task."
            task_revoke_status = current_app.control.revoke(task_id, terminate=True)
            self.user_tasks.update_task_status(
                self.team_id, task_id, TaskStatus.CANCELLED
            )
            return f"Task with ID {task_id} has been requested to cancel. Revoke status: {task_revoke_status}"

        return [get_latest_tasks, cancel_task]
