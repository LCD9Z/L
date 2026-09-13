# -*- coding: utf-8 -*-
"""llm_client.py - L4 全自动 · 大模型 API 客户端（火山方舟 Doubao API，纯标准库）

从 llm_config.json 读取配置（api_key / base_url / model），
提供 chat() 与 chat_json() 两个接口：
    chat(messages, ...)      -> 模型返回文本
    chat_json(messages, ...) -> 解析模型返回的 JSON（兼容 ```json 围栏 / 提取代码块）

用法：
    from llm_client import chat, chat_json
    resp = chat([{"role": "user", "content": "你好"}])
"""
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from typing import Optional

_I0 = 0

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm_config.json")
_DEFAULT_MODEL = "doubao-seed-1-6-250615"


def load_config():
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    # Secrets must come from the environment, not from distributable JSON files.
    for env_name, cfg_key in (("ARK_API_KEY", "api_key"), ("ARK_BASE_URL", "base_url"), ("ARK_MODEL", "model")):
        value = os.environ.get(env_name)
        if value:
            cfg[cfg_key] = value
    if not cfg.get("api_key"):
        raise RuntimeError("未配置 ARK_API_KEY：请设置环境变量或本地 .env 加载器")
    if not cfg.get("base_url"):
        raise RuntimeError("未配置 API base_url")
    return cfg


def _client():
    cfg = load_config()
    return cfg, ssl.create_default_context()


def chat(messages, model=None, temperature=0.3, max_tokens=4096, retries=3, timeout=300):
    """调用 Doubao API。messages 为 OpenAI 格式列表，返回文本。

    失败重试策略：指数退避（2**attempt 秒）；429 限频额外拉长至 5 秒起。
    """
    cfg, ctx = _client()
    mdl = model or cfg.get("model") or _DEFAULT_MODEL
    url = cfg["base_url"] + "/chat/completions"
    payload = {
        "model": mdl,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers={
                "Authorization": "Bearer " + cfg["api_key"],
                "Content-Type": "application/json",
            })
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                raw = r.read().decode("utf-8")
            d = json.loads(raw)
            return d["choices"][_I0]["message"]["content"]
        except urllib.error.HTTPError as e:
            last_err = e
            if attempt >= retries - 1:
                break
            # 429 限频：5 + 2**attempt 秒；其它 HTTP 错误：2**attempt 秒
            wait = (5 + 2 ** attempt) if e.code == 429 else 2 ** attempt
            time.sleep(wait)
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"LLM 调用失败: {last_err}")


def extract_json(text):
    """从模型返回文本中提取 JSON 对象。

    兼容：纯 JSON、```json 围栏、夹在文字中的 {...} 代码块。
    """
    if text is None:
        return None
    t = text.strip()
    if t.startswith("```"):
        # 去掉围栏
        lines = t.split("\n")
        body_lines = []
        for ln in lines:
            s = ln.strip()
            if s.startswith("```"):
                continue
            body_lines.append(ln)
        t = "\n".join(body_lines).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # 尝试找第一个 { 到最后一个 }
    i0 = t.find("{")
    i1 = t.rfind("}")
    if i0 >= 0 and i1 > i0:
        try:
            return json.loads(t[i0:i1 + 1])
        except json.JSONDecodeError:
            return None
    return None


def chat_json(messages, model=None, temperature=0.2, max_tokens=4096):
    """调用模型并要求 JSON 输出，返回解析后的 dict；解析失败返回 None。"""
    msgs = list(messages)
    msgs.append({"role": "user",
                 "content": "请只输出 JSON，不要包含任何解释文字、Markdown 代码块或其它内容。"})
    text = chat(msgs, model=model, temperature=temperature, max_tokens=max_tokens)
    return extract_json(text)


if __name__ == "__main__":
    print(chat([{"role": "user", "content": "用一句话回答：1+1等于几？"}]))
