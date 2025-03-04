from pydantic import BaseModel


class ModelConfig(BaseModel):
    """模型配置"""

    base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None


class LLMChatConfig(BaseModel):
    """聊天大模型配置"""

    base_url: str
    api_key: str
    model_name: str
    presets: dict[str, str]
    default_preset: str


class LLMSummaryConfig(ModelConfig):
    """摘要大模型配置"""


class EmbedConfig(ModelConfig):
    """嵌入模型配置"""

    dimension: int | None = None


class CensorConfig(BaseModel):
    """输出文本审核配置"""

    access_key_id: str | None = None
    access_key_secret: str | None = None


class Config(BaseModel):
    """Plugin Config Here"""

    chat: LLMChatConfig
    summary: LLMSummaryConfig
    embed: EmbedConfig
    censor: CensorConfig
