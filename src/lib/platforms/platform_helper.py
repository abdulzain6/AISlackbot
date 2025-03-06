from abc import ABC, abstractmethod
from typing import Dict, List
from typing import Optional, Union, Literal
from pydantic import BaseModel


class TextFormElement(BaseModel):
    type: Literal["text"]
    label: str
    action_id: str
    multiline: bool = False
    placeholder: Optional[str] = None
    initial_value: Optional[str] = None
    max_length: Optional[int] = None


FormElement = Union[TextFormElement]


class PlatformHelper(ABC):
    platform_name: str

    @property
    @abstractmethod
    def owner_uid(self) -> str:
        ...

    @property
    @abstractmethod
    def user_id(self) -> str:
        ...

    @property
    @abstractmethod
    def team_id(self) -> str:
        ...

    @abstractmethod
    def send_message(
        self, channel_id: str, message: str, thread_ts: str = None
    ):
        ...

    @abstractmethod
    def send_dm(self, message: str):
        ...

    @abstractmethod
    def get_chat_history(
        self, channel_id: str, limit: int = 10, thread_ts: str = None
    ) -> Optional[List[Dict[str, str]]]:
        ...

    @abstractmethod
    def send_form_dm(
        self,
        action_id: str,
        elements: list[FormElement],
        title: str = "Please complete this form",
        metadata: dict = None,
        user_id: str = None,
        extra_context: str = ""
    ) -> bool:
        """
        Send a form to a user via DM and return success status
        """
        ...