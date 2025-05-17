from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

class LLMConfig(BaseModel):
    model_provider: str
    model: str
    llm_kwargs: dict[str, str] = {}

    def to_llm(self) -> BaseChatModel:
        init_params = {
            "model_provider": self.model_provider,
            "model": self.model,
            **self.llm_kwargs
        }
        llm = init_chat_model(**init_params)
        return llm
