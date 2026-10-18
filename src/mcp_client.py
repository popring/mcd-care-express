# -*- coding: utf-8 -*-
"""麦当劳 MCP 的 Streamable HTTP 客户端。

设计约束：
    1. 零第三方依赖，只用标准库；
    2. 传输层可替换 —— 离线时用 FixtureTransport 读 fixtures/ 下的预置响应，
       联网时用 HttpTransport 直连 https://mcp.mcd.cn。业务逻辑因此完全可测；
    3. 不做猜测：接口返回什么就解析什么，解析不出来就原样返回文本，绝不补数字。

协议要点（来自官方 README 与 MCP Streamable HTTP 规范）：
    * 接入地址 https://mcp.mcd.cn，传输协议 Streamable HTTP；
    * 请求头必须携带 Authorization: Bearer <TOKEN>；
    * 服务端通过响应头 Mcp-Session-Id 下发会话 ID，后续请求需原样回传；
    * 响应体可能是裸 JSON，也可能是 SSE 的 `data:` 行，两种都要能解。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

PROTOCOL_VERSION = "2024-11-05"
DEFAULT_ENDPOINT = "https://mcp.mcd.cn"
CLIENT_INFO = {"name": "mcd-care-express", "version": "1.0.0"}


class McpError(RuntimeError):
    """MCP 协议层或传输层错误。"""


class Transport:
    """传输层接口：把一个 JSON-RPC 方法调用换成结果 dict。"""

    def call(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:  # pragma: no cover
        raise NotImplementedError


class HttpTransport(Transport):
    """直连麦当劳 MCP 的传输层。"""

    def __init__(self, token: str, endpoint: str = DEFAULT_ENDPOINT, timeout: float = 20.0):
        if not token:
            raise ValueError("缺少 MCP Token，无法建立连接")
        self._endpoint = endpoint
        self._timeout = timeout
        self._headers = {
            "Authorization": "Bearer %s" % token,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self._session_id: Optional[str] = None
        self._rpc_id = 0

    # -- 底层 ------------------------------------------------------------
    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = dict(self._headers)
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        request = urllib.request.Request(
            self._endpoint, data=data, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read().decode("utf-8", "replace")
                new_session = response.headers.get("Mcp-Session-Id")
                if new_session:
                    self._session_id = new_session
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:200]
            except Exception:  # noqa: BLE001 - 读取错误体失败也不应掩盖主错误
                detail = ""
            if exc.code == 401:
                raise McpError(
                    "401 未授权：Token 无效或已过期；同时确认 endpoint 为 "
                    "https://mcp.mcd.cn 且 Authorization 头已带上真实 Token"
                ) from exc
            if exc.code == 429:
                raise McpError("429 限流：超过 600 次/分钟，请降低调用频率") from exc
            raise McpError("HTTP %s：%s" % (exc.code, detail)) from exc
        except urllib.error.URLError as exc:
            raise McpError("网络不可达：%s" % exc.reason) from exc
        return self._parse_body(raw)

    @staticmethod
    def _parse_body(raw: str) -> Dict[str, Any]:
        """Streamable HTTP 可能返回裸 JSON，也可能返回 SSE（data: {...}）。"""
        text = raw.strip()
        if not text:
            raise McpError("服务端返回空响应")
        if text.startswith("{"):
            return json.loads(text)
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                body = line[5:].strip()
                if body and body != "[DONE]":
                    return json.loads(body)
        raise McpError("无法解析响应体：%s" % text[:200])

    # -- 传输层接口 ------------------------------------------------------
    def call(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        is_notification = method.startswith("notifications/")
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not is_notification:
            self._rpc_id += 1
            payload["id"] = self._rpc_id
        if params:
            payload["params"] = params
        result = self._post(payload)
        if is_notification:
            return {}
        if "error" in result:
            error = result["error"] or {}
            raise McpError("MCP error %s：%s" % (error.get("code"), error.get("message")))
        return result.get("result") or {}


class FixtureTransport(Transport):
    """离线传输层：按 tool 名返回 fixtures 中预置的响应。

    存在的意义是让整套业务逻辑在没有 Token、不联网的情况下也能端到端跑通，
    demo 因此同时是一次回归测试。
    """

    def __init__(self, responses: Dict[str, Any]):
        self._responses = dict(responses)
        self.calls: List[Dict[str, Any]] = []

    def call(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        record = {"method": method, "params": params}
        self.calls.append(record)
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": {"name": "mcd-mcp", "version": "1.0.9"},
                "capabilities": {"tools": {}},
            }
        if method.startswith("notifications/"):
            return {}
        if method == "tools/list":
            return {"tools": self._responses.get("_tools", [])}
        if method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments") or {}
            record["tool"] = name
            record["arguments"] = arguments
            if name not in self._responses:
                raise McpError("fixture 缺失：%s（请在 fixtures/ 中补充该工具的响应）" % name)
            payload = self._responses[name]
            text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
            return {"content": [{"type": "text", "text": text}], "isError": False}
        return {}


def _text_of(result: Dict[str, Any]) -> str:
    """取 tools/call 结果里的文本部分。"""
    chunks = []
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            chunks.append(item.get("text") or "")
    return "\n".join(chunks).strip()


def extract_payload(result: Dict[str, Any]) -> Any:
    """把 tools/call 的结果还原成 Python 对象。

    优先用 structuredContent；没有就尝试把文本当 JSON 解析；
    仍失败则原样返回文本，并打上 _text 键，绝不猜测字段。
    """
    structured = result.get("structuredContent")
    if structured:
        return structured
    text = _text_of(result)
    if not text:
        return {}
    try:
        return json.loads(text)
    except ValueError:
        return {"_text": text}


class McpClient:
    """对传输层做一层薄封装，暴露 initialize / list_tools / call_tool。"""

    def __init__(self, transport: Transport):
        self._transport = transport
        self._ready = False

    def _ensure_initialized(self) -> None:
        if self._ready:
            return
        self._transport.call(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )
        self._transport.call("notifications/initialized", {})
        self._ready = True

    def list_tools(self) -> List[Dict[str, Any]]:
        self._ensure_initialized()
        return self._transport.call("tools/list", {}).get("tools") or []

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        self._ensure_initialized()
        result = self._transport.call("tools/call", {"name": name, "arguments": arguments or {}})
        if result.get("isError"):
            raise McpError("工具 %s 返回错误：%s" % (name, _text_of(result)[:300]))
        return extract_payload(result)

    @property
    def call_log(self) -> List[Dict[str, Any]]:
        """传输层记录的调用序列（只有 FixtureTransport 提供）。"""
        return getattr(self._transport, "calls", [])


def build_client(token: str = "", endpoint: str = DEFAULT_ENDPOINT) -> McpClient:
    """按有无 Token 选择传输层。没有 Token 时调用工具会直接报 McpError。"""
    return McpClient(HttpTransport(token=token, endpoint=endpoint))


def build_offline_client(responses: Dict[str, Any]) -> McpClient:
    return McpClient(FixtureTransport(responses))
