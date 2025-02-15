from typing import TypedDict
from langchain.chat_models import init_chat_model
from typing import TypedDict

class LLMConfig(TypedDict):
    model_provider: str
    model: str
    llm_kwargs: dict[str, str] = {}


def initialize_llm(config: LLMConfig):
    init_params = {
        "model_provider": config["model_provider"],
        "model": config["model"],
        **config.get("llm_kwargs")
    }
    llm = init_chat_model(**init_params)
    return llm
