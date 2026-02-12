"""
LLM 客户端模块
封装 DeepSeek API 调用，内置自动重试和 validator 校验。
"""
import json
import time
from openai import OpenAI
import config


class LLMClient:
    """DeepSeek LLM 客户端，基于 OpenAI SDK"""

    def __init__(self, api_key=None, base_url=None, model=None):
        self.api_key = api_key or config.API_KEY
        self.base_url = base_url or config.BASE_URL
        self.model = model or config.MODEL

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=600.0,  # 10 minutes timeout for reasoner models
        )

    def query(self, system_prompt: str, user_content: str, json_mode: bool = True, model: str = None):
        """
        单次调用 LLM，成功返回解析后的结果，失败抛出异常。
        """
        kwargs = {
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content

        if json_mode:
            return json.loads(content)
        else:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return content

    def call_with_retry(self, system_prompt: str, user_content: str,
                        json_mode: bool = True, validator=None,
                        retry_delay: float = 2.0, model: str = None):
        """
        循环调用 LLM 直到成功（通过 validator 校验）。
        
        Args:
            system_prompt: 系统提示词
            user_content: 用户消息
            json_mode: 是否启用 JSON 模式
            validator: 可选的验证函数，接受 LLM 返回值，通过返回 True
            retry_delay: 重试间隔（秒）
            model: 可选的模型名称覆盖默认值
        
        Returns:
            LLM 返回结果（已通过 validator 校验）
        """
        while True:
            try:
                result = self.query(system_prompt, user_content, json_mode=json_mode, model=model)

                if validator:
                    if validator(result):
                        return result
                    else:
                        print(f"[LLM] 返回结果未通过验证，{retry_delay}秒后重试...")
                        time.sleep(retry_delay)
                        retry_delay = min(retry_delay * 2, 60.0)  # Exponential backoff, max 60s
                        continue

                return result

            except Exception as e:
                print(f"[LLM] 调用失败: {e}。{retry_delay}秒后重试...")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60.0)  # Exponential backoff, max 60s


if __name__ == "__main__":
    client = LLMClient()
    print("正在测试 LLM 客户端...")
    try:
        resp = client.call_with_retry(
            "你是一个乐于助人的助手。请输出 JSON。",
            '用 JSON 格式说你好，使用 "message" 键。',
            json_mode=True,
        )
        print(f"测试成功: {resp}")
    except Exception as e:
        print(f"测试失败: {e}")
