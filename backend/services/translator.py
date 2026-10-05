import os
import json
import logging
import re
import time
from typing import List, Dict, Any, Optional, Callable
import httpx

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

    def translate_segments(
        self,
        segments: List[Dict[str, Any]],
        source_language: str = "auto",
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Translates a list of ASR segments into natural Chinese dubbing subtitles.
        Controls Chinese character length based on segment duration for voiceover pacing.
        """
        if not segments:
            return []

        if not self.api_key:
            raise ValueError("DeepSeek API Key 未提供，请在前端设置中输入有效的 DeepSeek API Key")

        total = len(segments)
        batch_size = 40
        batches = [segments[i:i + batch_size] for i in range(0, total, batch_size)]
        translated_results: List[Dict[str, Any]] = []

        logger.info(f"Starting DeepSeek translation ({self.model_name}) for {total} segments in {len(batches)} batches")

        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("all_proxy")
        client_kwargs = {"timeout": 120.0}
        if proxy:
            client_kwargs["proxy"] = proxy

        url = self._get_chat_url()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        system_prompt = (
            "你是一位专业的电影与视频本地化配音翻译专家。"
            "你的任务是将输入的带时间戳的语音识别片段翻译为极其自然、地道、适合中文普通话配音朗读的中文语句。\n"
            "核心要求：\n"
            "1. 【最高优先级约束：死卡汉字上限】：每句翻译的汉字字数必须严格小于等于每个分段给出的 `max_chars` 字段！普通话正常语速约为每秒 3.5~3.8 个汉字。超字将直接导致配音念不完而引发严重的音画脱节！宁可意译精炼短小，严禁超字！\n"
            "2. 【口语化与流畅度】：符合中文母语听觉习惯，通俗流畅，避免生硬的书面语或翻译腔。\n"
            "3. 【语境连贯】：结合上下文语意，保持人称和专有名词前后一致。\n"
            "4. 【严格输出格式】：必须返回一个 JSON 数组（或根对象包含 `subtitles` 数组），每个对象包含：\n"
            "   - `id`: 原分段id (整数)\n"
            "   - `translated_text`: 对应的中文配音文本 (字符串，不含特殊标记，字数严格 ≤ max_chars)\n"
            "只返回纯 JSON，严禁附带任何 Markdown 代码块外的文字解释。"
        )

        with httpx.Client(**client_kwargs) as client:
            for b_idx, batch in enumerate(batches, 1):
                if progress_callback:
                    p = (b_idx - 1) / len(batches) * 100
                    progress_callback(p, f"DeepSeek ({self.model_name}) 正在翻译字幕 (第 {b_idx}/{len(batches)} 批)...")

                batch_input = [
                    {
                        "id": seg["id"],
                        "start": seg["start"],
                        "end": seg["end"],
                        "duration": round(seg["end"] - seg["start"], 2),
                        "max_chars": max(3, int(round((seg["end"] - seg["start"]) * 3.8))),
                        "text": seg["text"]
                    }
                    for seg in batch
                ]

                user_prompt = f"以下是待翻译的字幕片段（源语言: {source_language}）：\n{json.dumps(batch_input, ensure_ascii=False, indent=2)}\n\n请输出翻译后的 JSON 数组："

                payload = {
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.3
                }

                # Try response_format json_object if model supports it
                # Some third-party providers error on response_format, so keep standard
                try:
                    resp = client.post(url, json=payload, headers=headers)
                    if resp.status_code != 200:
                        err_text = resp.text
                        try:
                            err_json = resp.json()
                            err_text = err_json.get("error", {}).get("message") or err_text
                        except Exception:
                            pass
                        raise RuntimeError(f"DeepSeek API 错误 [{resp.status_code}]: {err_text}")

                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        raise RuntimeError(f"DeepSeek 返回空 choices: {data}")

                    content_text = choices[0].get("message", {}).get("content", "").strip()
                    
                    # Strip markdown fence if present
                    if content_text.startswith("```json"):
                        content_text = content_text[7:]
                    elif content_text.startswith("```"):
                        content_text = content_text[3:]
                    if content_text.endswith("```"):
                        content_text = content_text[:-3]
                    content_text = content_text.strip()

                    # Find JSON array or object
                    match = re.search(r"(\[.*\]|\{.*\})", content_text, re.DOTALL)
                    if match:
                        content_text = match.group(1)

                    parsed_batch = json.loads(content_text)
                    if isinstance(parsed_batch, dict):
                        # If wrapped like {"subtitles": [...]}
                        for v in parsed_batch.values():
                            if isinstance(v, list):
                                parsed_batch = v
                                break

                    if not isinstance(parsed_batch, list):
                        raise ValueError(f"解析后的翻译结果非列表: {content_text[:100]}")

                    trans_map = {item.get("id"): str(item.get("translated_text", "")).strip() for item in parsed_batch}

                    for seg in batch:
                        t_text = trans_map.get(seg["id"]) or seg["text"]
                        translated_results.append({
                            "id": seg["id"],
                            "start": seg["start"],
                            "end": seg["end"],
                            "duration": round(seg["end"] - seg["start"], 3),
                            "original_text": seg["text"],
                            "translated_text": t_text
                        })

                except Exception as e:
                    logger.error(f"DeepSeek translation failed for batch {b_idx}: {e}")
                    raise RuntimeError(f"DeepSeek 翻译第 {b_idx} 批字幕失败: {str(e)}")

        if progress_callback:
            progress_callback(100.0, f"字幕翻译完成，共生成 {len(translated_results)} 句配音译文")

        return translated_results
