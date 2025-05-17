from abc import ABC, abstractmethod
from io import IOBase
from typing import Dict, List, Tuple
from langchain_core.messages import BaseMessage
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

    @abstractmethod
    def get_file_name(self, file_id: str) -> str:
        ...
        
    @abstractmethod
    def get_file_bytes(self, file_id: str) -> bytes:
        ...

    @abstractmethod
    def get_recent_file_info(self, *args, **kwargs) -> List[dict]: ...

    @abstractmethod
    def read_file(self, file_id: str) -> str: ...

    @property
    @abstractmethod
    def owner_uid(self) -> str: ...

    @property
    @abstractmethod
    def user_id(self) -> str: ...

    @property
    @abstractmethod
    def team_id(self) -> str: ...

    @abstractmethod
    def send_message(self, *args, **kwargs): ...

    @abstractmethod
    def send_dm(self, message: str): ...

    @abstractmethod
    def get_chat_history(self, **kwargs) -> Optional[List[BaseMessage]]: ...

    @abstractmethod
    def send_form_dm(
        self,
        action_id: str,
        elements: list[FormElement],
        title: str = "Please complete this form",
        metadata: dict | None = None,
        user_id: str | None = None,
        extra_context: str = "",
    ) -> bool:
        """
        Send a form to a user via DM and return success status
        """
        ...

    @abstractmethod
    def send_picture(self, image_url: str, alt_text: str, **kwargs): ...

    @abstractmethod
    def send_file(
        self, file: Optional[Union[str, bytes, IOBase]], title: str, **kwargs
    ): ...
