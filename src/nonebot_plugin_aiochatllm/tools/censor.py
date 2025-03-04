import asyncio
import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import httpx
from nonebot import logger


class AliyunCensor:
    """内容审核模块"""

    def __init__(self, config:dict[str, Any]) -> None:
        self.url: str = "https://green-cip.cn-shanghai.aliyuncs.com"
        self.key_id: str = config["key_id"]
        self.key_secret: str = config["key_secret"]

    def _split_text(self, content: str) -> list[str]:
        """极端条件下的文本分割"""
        if not content:
            return []
        chunks = []
        for i in range(0, len(content), 600):
            chunks.append(content[i:i + 600])
        return chunks

    async def _check_single_text(self, content: str) -> bool:
        """单段文本审核"""
        try:
            params_a: dict[str, str] = {
                'Format': 'JSON',
                'Version': '2022-03-02',
                'AccessKeyId': self.key_id,
                'SignatureMethod': 'HMAC-SHA1',
                'Timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'SignatureVersion': '1.0',
                'SignatureNonce': str(uuid.uuid4()),
                'Action': 'TextModerationPlus',
                'Service': 'chat_detection_pro',
                'ServiceParameters': json.dumps({'content': content})
            }

            sorted_params: list = sorted(params_a.items())

            def encode(s: Any) -> str:
                return quote_plus(str(s)).replace('+', '%20').replace('*', '%2A').replace('%7E', '~')

            canonicalized_query = '&'.join(f'{encode(k)}={encode(v)}' for k, v in sorted_params)
            string_to_sign = f'POST&{encode("/")}&{encode(canonicalized_query)}'
            key = self.key_secret + '&'
            signature = base64.b64encode(
                hmac.new(
                    key.encode('utf-8'),
                    string_to_sign.encode('utf-8'),
                    hashlib.sha1
                ).digest()
            ).decode('utf-8')

            params_a['Signature'] = signature

            async with httpx.AsyncClient() as client:
                response = await client.post(self.url, params=params_a)
                if response.status_code != 200:
                    logger.error(f"内容审核HTTP状态错误: {response.status_code}")
                    return False
                result = response.json()
                if 'Data' not in result:
                    logger.error(f"内容审核返回数据异常: {result}")
                    return False
                risk_level = result['Data'].get('RiskLevel', '').lower()
                logger.debug(f"内容审核结果: {risk_level}")
                return bool(risk_level != 'high')
        except httpx.RequestError as e:
            logger.error(f"内容审核网络请求错误: {e!s}")
            return False
        except Exception as e:
            logger.error(f"内容审核发生未知错误: {e!s}")
            return False

    async def check_text(self, content: str) -> bool:
        """所有文本审核"""
        try:
            if not content:
                return True
            if len(content) <= 600:
                return await self._check_single_text(content)
            chunks = self._split_text(content)
            tasks = [self._check_single_text(chunk) for chunk in chunks]
            results = await asyncio.gather(*tasks)
            return all(results)
        except Exception:
            return False
