import os
import json
import logging
import re
import time
import math
from typing import List, Dict, Any, Optional, Callable
import httpx

from backend.services.pacing import DEFAULT_SPEAKING_RATE, speech_character_count

logger = logging.getLogger(__name__)

class DeepSeekTranslator:
    """Translation service powered by DeepSeek / OpenAI-compatible API with structured JSON output."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com/v1",
        model_name: str = "deepseek4.1flash"
    ):
        self.api_key = api_key.strip()
        self.base_url = (base_url or "https://api.deepseek.com/v1").strip().rstrip("/")
        self.model_name = (model_name or "deepseek4.1flash").strip()

    def _get_chat_url(self) -> str:
        """Constructs chat completions endpoint URL from base_url."""
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/chat/completions"

    @classmethod
    def test_connection(cls, api_key: str, base_url: str, model_name: str) -> Dict[str, Any]:
        """Tests connectivity and authentication with DeepSeek API."""
        if not api_key:
            return {"status": "error", "error": "API Key 不能为空"}

        translator = cls(api_key=api_key, base_url=base_url, model_name=model_name)
        url = translator._get_chat_url()

        headers = {
            "Authorization": f"Bearer {translator.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": translator.model_name,
            "messages": [
                {"role": "user", "content": "Hi, reply 'OK' only."}
            ],
            "max_tokens": 10,
            "temperature": 0.1
        }

        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("all_proxy")
        client_kwargs = {"timeout": 20.0}
        if proxy:
            client_kwargs["proxy"] = proxy

        t0 = time.time()
        try:
            with httpx.Client(**client_kwargs) as client:
                resp = client.post(url, json=payload, headers=headers)
                latency = int((time.time() - t0) * 1000)

                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return {
                        "status": "ok",
                        "latency_ms": latency,
                        "model": translator.model_name,
                        "reply": content.strip(),
                        "message": f"连接成功！DeepSeek 响应正常 (耗时 {latency}ms)"
                    }
                else:
                    err_msg = resp.text
                    try:
                        err_json = resp.json()
                        err_msg = err_json.get("error", {}).get("message") or err_msg
                    except Exception:
                        pass
                    return {
                        "status": "error",
                        "status_code": resp.status_code,
                        "error": f"API 响应错误 [{resp.status_code}]: {err_msg}"
                    }
        except httpx.ConnectTimeout:
            return {"status": "error", "error": f"连接超时 (20s)，请检查 Base URL '{url}' 是否可访问或是否需要网络代理"}
        except httpx.ConnectError as e:
            return {"status": "error", "error": f"无法连接到目标服务器 ({url}): {str(e)}"}
        except Exception as e:
            return {"status": "error", "error": f"请求异常: {str(e)}"}

    @staticmethod
    def _parse_translations(content: str) -> List[Dict[str, Any]]:
        content = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", content.strip())
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            parsed = next((value for value in parsed.values() if isinstance(value, list)), None)
        if not isinstance(parsed, list):
            raise ValueError("翻译结果必须是 JSON 数组")
        return parsed

    def translate_segments(
        self,
        segments: List[Dict[str, Any]],
        source_language: str = "auto",
        progress_callback: Optional[Callable[[float, str], None]] = None,
        full_context: str = "",
        speaking_rate: float = DEFAULT_SPEAKING_RATE,
    ) -> List[Dict[str, Any]]:
        """Translate semantic blocks with full context while retaining source timing."""
        if not segments:
            return []
        if not self.api_key:
            raise ValueError("DeepSeek API Key 未提供，请在前端设置中输入有效的 DeepSeek API Key")
        if not math.isfinite(speaking_rate) or speaking_rate <= 0:
            raise ValueError("朗读语速必须为正数")
        batches = [segments[i:i + 40] for i in range(0, len(segments), 40)]
        results = []
        system_prompt = (
            "你是视频本地化配音翻译专家。先理解全文上下文，再逐段输出自然、连贯的中文配音稿。\n"
            "必须保持每个输入 id 的内容对应关系，不得跨段挪动内容、合并、拆分或遗漏段落。\n"
            "每段文字（不计标点空白）的字数必须 <= max_chars，超限时精简意译，保留关键事实。\n"
            "长句使用自然的中文标点划分气口；不要为了凑字数添加内容。\n"
            "只输出 JSON 数组，每项为 {\"id\": 原id, \"translated_text\": \"中文文案\"}。"
        )
        client_kwargs = {"timeout": 120.0}
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("all_proxy")
        if proxy:
            client_kwargs["proxy"] = proxy
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        with httpx.Client(**client_kwargs) as client:
            for batch_index, batch in enumerate(batches, 1):
                if progress_callback:
                    progress_callback(
                        (batch_index - 1) / len(batches) * 100,
                        f"按原时间轴翻译 (第 {batch_index}/{len(batches)} 批)...",
                    )
                batch_input = []
                for segment in batch:
                    duration = segment["end"] - segment["start"]
                    if not math.isfinite(duration) or duration <= 0:
                        raise ValueError(f"段落 #{segment['id']} 的时间窗口无效")
                    batch_input.append({
                        "id": segment["id"], "start": segment["start"], "end": segment["end"],
                        "duration": duration, "max_chars": max(1, int(duration * speaking_rate)),
                        "text": segment["text"],
                    })
                user_prompt = (
                    f"源语言: {source_language}\n全文上下文（仅供理解，不另行翻译）：\n"
                    f"{full_context or ' '.join(s['text'] for s in segments)}\n\n"
                    f"本批待翻译段落：\n{json.dumps(batch_input, ensure_ascii=False)}"
                )
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
                limits = {item["id"]: item["max_chars"] for item in batch_input}
                for attempt in range(2):
                    response = client.post(
                        self._get_chat_url(),
                        json={"model": self.model_name, "messages": messages, "temperature": 0.3},
                        headers=headers,
                    )
                    if response.status_code != 200:
                        raise RuntimeError(f"DeepSeek 翻译失败 [{response.status_code}]: {response.text}")
                    content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    try:
                        parsed = self._parse_translations(content)
                        if not all(isinstance(item, dict) and isinstance(item.get("translated_text"), str) for item in parsed):
                            raise ValueError("每个段落必须包含字符串 translated_text")
                        translated = {int(item["id"]): str(item["translated_text"]).strip() for item in parsed}
                        if len(parsed) != len(batch) or set(translated) != set(limits):
                            raise ValueError("段落 ID 必须与输入一一对应，不能重复或遗漏")
                        for segment_id, text in translated.items():
                            characters = speech_character_count(text)
                            if not characters or characters > limits[segment_id]:
                                raise ValueError(
                                    f"段落 #{segment_id} 有 {characters} 字，必须为 1~{limits[segment_id]} 字"
                                )
                        break
                    except (ValueError, TypeError, KeyError) as error:
                        if attempt == 1:
                            raise RuntimeError(f"翻译结果无法满足时间窗口: {error}") from error
                        messages.extend([
                            {"role": "assistant", "content": content},
                            {"role": "user", "content": f"请修正整批 JSON，保持原意且满足所有约束。错误：{error}"},
                        ])
                results.extend({
                    **segment,
                    "original_text": segment["text"],
                    "translated_text": translated[segment["id"]],
                    "duration": round(segment["end"] - segment["start"], 3),
                } for segment in batch)
        if progress_callback:
            progress_callback(100.0, f"完成 {len(results)} 个原时间轴段落的翻译")
        return results
