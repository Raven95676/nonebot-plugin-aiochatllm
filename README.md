<div align="center">
  <a href="https://v2.nonebot.dev/store"><img src="https://raw.githubusercontent.com/A-kirami/nonebot-plugin-template/refs/heads/resources/nbp_logo.png" width="180" height="180" alt="NoneBotPluginLogo"></a>
  <br>
  <p><img src="https://raw.githubusercontent.com/A-kirami/nonebot-plugin-template/refs/heads/resources/NoneBotPlugin.svg" width="240" alt="NoneBotPluginText"></p>
</div>

<div align="center">

# nonebot-plugin-aiochatllm

_✨ 多合一LLM聊天插件 ✨_


<a href="./LICENSE">
    <img alt="GitHub License" src="https://img.shields.io/github/license/Raven95676/nonebot-plugin-aiochatllm">
</a>
<a href="https://pypi.python.org/pypi/nonebot-plugin-aiochatllm">
    <img src="https://img.shields.io/pypi/v/nonebot-plugin-aiochatllm.svg" alt="pypi">
</a>
<img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="python">

</div>

> [!important]
> 本项目仅支持 **Python3.10及以上** 的版本

> [!note]
> 代码质量不高。作者没有什么时间维护本项目。

## 项目依赖

- [nonebot-plugin-alconna](https://github.com/nonebot/plugin-alconna)
- [nonebot-plugin-localstore](https://github.com/nonebot/plugin-localstore)
- [nonebot-plugin-uninfo](https://github.com/RF-Tar-Railt/nonebot-plugin-uninfo)
- [nonebot-plugin-apscheduler](https://github.com/nonebot/plugin-apscheduler)

## 介绍

本插件为Bot提供LLM聊天服务，包含输出内容审核、长期记忆。

## 安装

前置步骤：将`pyproject.toml`内的`3.9`修改为`3.10`。

<details open>
<summary>使用 nb-cli 安装</summary>
在 nonebot2 项目的根目录下打开命令行, 输入以下指令即可安装

    nb plugin install nonebot-plugin-aiochatllm

</details>

<details>
<summary>使用包管理器安装</summary>
在 nonebot2 项目的插件目录下, 打开命令行, 根据你使用的包管理器, 输入相应的安装命令

<details>
<summary>pip</summary>

    pip install nonebot-plugin-aiochatllm
</details>
<details>
<summary>pdm</summary>

    pdm add nonebot-plugin-aiochatllm
</details>

打开 nonebot2 项目根目录下的 `pyproject.toml` 文件, 在 `[tool.nonebot]` 部分追加写入

    plugins = ["nonebot_plugin_aiochatllm"]

</details>

## 配置

| 配置项                    | 描述                                      | 示例值或说明                                 |
| ------------------------- | ----------------------------------------- | -------------------------------------------- |
| **聊天大模型配置**        |                                           |                                              |
| CHAT__BASE_URL            | 聊天服务的基本URL                         | `https://api.example.com`                    |
| CHAT__API_KEY             | 访问聊天服务所需的API密钥                 | `your_chat_api_key_here`                     |
| CHAT__MODEL_NAME          | 使用的聊天模型名称                        | `ChatModel`                                  |
| CHAT__PRESETS             | 预设字典                                 | `{"preset1": "value1", "preset2": "value2"}` |
| CHAT__DEFAULT_PRESET      | 默认使用的预设值                          | `default`                                    |
| **摘要大模型配置**        |                                           |                                              |
| SUMMARY__BASE_URL         | 摘要服务的基本URL                         | `https://api.example.com`                    |
| SUMMARY__API_KEY          | 访问摘要服务所需的API密钥                 | `your_summary_api_key_here`                  |
| SUMMARY__MODEL_NAME       | 使用的摘要模型名称                        | `SummaryModel`                               |
| **嵌入模型配置**          | 配置后**禁止更改**                        |                                              |
| EMBED__BASE_URL           | 嵌入服务的基本URL                         | `https://api.example.com`                    |
| EMBED__API_KEY            | 访问嵌入服务所需的API密钥                 | `your_embed_api_key_here`                    |
| EMBED__MODEL_NAME         | 使用的嵌入模型名称                        | `EmbedModel`                                 |
| EMBED__DIMENSION          | 嵌入向量的维度                            | `1024`                                       |
| **阿里云内容审核配置**    |                                           |                                              |
| CENSOR__ACCESS_KEY_ID     | 访问阿里云内容审核服务的Access Key ID     | `your_censor_access_key_id_here`             |
| CENSOR__ACCESS_KEY_SECRET | 访问阿里云内容审核服务的Access Key Secret | `your_censor_access_key_secret_here`         |

**注意事项：**
- 嵌入模型配置一旦设置后禁止更改，请谨慎配置。

## TODO

- 完善命令
- 完善配置
- 完善记忆系统
- 增加识图功能
- 增加语音识别
- 增加更多向量数据库
