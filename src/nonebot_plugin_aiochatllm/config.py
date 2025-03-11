from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """模型配置"""

    base_url: str | None = Field(default=None)
    api_key: str | None = Field(default=None)
    model_name: str | None = Field(default=None)


class LLMChatConfig(ModelConfig):
    """聊天大模型配置"""

    presets: dict[str, str] = Field(default={"default": "I'm a helpful AI assistant."})
    default_preset: str = Field(default="default")


class LLMSummaryConfig(ModelConfig):
    """摘要大模型配置"""


class EmbedConfig(ModelConfig):
    """嵌入模型配置"""

    dimension: int | None = Field(default=None)


class CensorConfig(BaseModel):
    """输出文本审核配置"""

    access_key_id: str | None = Field(default=None)
    access_key_secret: str | None = Field(default=None)


class Config(BaseModel):
    """Plugin Config Here"""

    chat: LLMChatConfig = Field(
        default=LLMChatConfig(
            presets={"default": "I'm a helpful AI assistant."},
            default_preset="default"
        )
    )
    summary: LLMSummaryConfig | None = Field(default=None)
    embed: EmbedConfig | None = Field(default=None)
    censor: CensorConfig | None = Field(default=None)
