#!/usr/bin/env python3
"""
NVIDIA DGX Spark / GB10 - 透明会话持久化与 100 槽位 FIFO 管理代理
=============================================================================
功能特性:
1. 透明拦截 /v1/chat/completions，提取会话特征指纹 (Session ID)。
2. 自动检测 NVMe SSD 是否有该会话历史快照；若被淘汰，自动从磁盘秒级 Restore 槽位。
3. 响应完成后自动异步触发 Action=Save 存盘，保证最新对话状态不丢失。
4. 维护 100 个会话快照的严格先进先出 (FIFO) 淘汰队列，超额自动清理最旧文件。
5. 原生支持 SSE 流式打字机输出 (Stream) 与所有 OpenAI 兼容客户端零感接入。
"""

import os
import json
import time
import hashlib
import logging
import asyncio
from typing import Optional, List, Dict, Any
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# -----------------------------------------------------------------------------
# 配置参数
# -----------------------------------------------------------------------------
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001")
PROXY_HOST = os.getenv("PROXY_HOST", "0.0.0.0")
PROXY_PORT = int(os.getenv("PROXY_PORT", "8000"))
SLOT_CACHE_DIR = Path(os.getenv("SLOT_CACHE_DIR", "/home/admin/slot_cache"))
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "500"))
FIFO_INDEX_FILE = SLOT_CACHE_DIR / "fifo_index.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("SlotFIFOProxy")

app = FastAPI(title="Qwen3.8 Flash-Next Slot FIFO Proxy")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 确保存储目录存在
SLOT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class FIFOManager:
    """管理 500 会话快照的 FIFO 淘汰逻辑"""

    def __init__(self, index_file: Path, max_sessions: int):
        self.index_file = index_file
        self.max_sessions = max_sessions
        self.lock = asyncio.Lock()
        self.queue: List[str] = self._load_index()

    def _load_index(self) -> List[str]:
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("queue", [])
            except Exception as e:
                logger.error(f"读取 FIFO 索引失败: {e}")
        return []

    def _save_index(self):
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump({"queue": self.queue, "updated_at": time.time()}, f, indent=2)
        except Exception as e:
            logger.error(f"写入 FIFO 索引失败: {e}")

    async def record_session(self, filename: str):
        async with self.lock:
            # 若已在队列中，移到队列末尾 (最近更新)
            if filename in self.queue:
                self.queue.remove(filename)
            self.queue.append(filename)

            # 超出上限，按 FIFO 淘汰最旧的会话快照
            while len(self.queue) > self.max_sessions:
                oldest_file = self.queue.pop(0)
                oldest_path = SLOT_CACHE_DIR / oldest_file
                if oldest_path.exists():
                    try:
                        oldest_path.unlink()
                        logger.info(f"🗑️ [FIFO 淘汰] 已清理最旧历史会话快照: {oldest_file} (当前留存: {len(self.queue)}/{self.max_sessions})")
                    except Exception as e:
                        logger.error(f"清理文件 {oldest_file} 失败: {e}")

            self._save_index()


fifo_mgr = FIFOManager(FIFO_INDEX_FILE, MAX_SESSIONS)
client = httpx.AsyncClient(base_url=BACKEND_URL, timeout=httpx.Timeout(300.0, connect=10.0))


def extract_session_id(body: dict, headers: dict) -> str:
    """从请求中提取唯一会话特征指纹"""
    # 1. 优先提取显式 header 或字段
    for h in ["x-session-id", "x-conversation-id", "session-id"]:
        if h in headers:
            return f"sess_{headers[h]}"

    for field in ["conversation_id", "session_id"]:
        if field in body and body[field]:
            return f"sess_{body[field]}"

    # 2. 从消息树提取锚点 (首条 system + 首条 user 消息)
    messages = body.get("messages", [])
    sys_content = ""
    user_content = ""
    for msg in messages:
        role = msg.get("role")
        content = str(msg.get("content", ""))
        if role == "system" and not sys_content:
            sys_content = content
        elif role == "user" and not user_content:
            user_content = content
            break

    anchor = f"{sys_content}::{user_content}"
    if not anchor.strip(":"):
        anchor = f"default_{time.time()}"

    h = hashlib.sha256(anchor.encode("utf-8")).hexdigest()[:16]
    return f"sess_{h}"


async def get_target_slot(session_filename: str) -> Optional[int]:
    """检查槽位状态并按需执行 Restore 读盘"""
    try:
        resp = await client.get("/slots")
        if resp.status_code != 200:
            return None
        slots = resp.json()
    except Exception as e:
        logger.error(f"获取槽位状态失败: {e}")
        return None

    filepath = SLOT_CACHE_DIR / session_filename

    # 如果有快照且未被加载，挑选最空闲/最久没用的槽位进行恢复
    if filepath.exists():
        idle_slots = [s for s in slots if not s.get("is_processing", False)]
        if idle_slots:
            target_slot = idle_slots[0]["id"]
            try:
                t0 = time.time()
                restore_resp = await client.post(
                    f"/slots/{target_slot}?action=restore",
                    json={"filename": session_filename}
                )
                cost_ms = (time.time() - t0) * 1000
                if restore_resp.status_code == 200:
                    logger.info(f"⚡ [NVMe 读盘恢复] 成功将会话 {session_filename} 载入 Slot {target_slot}，耗时 {cost_ms:.1f}ms！")
                    return target_slot
            except Exception as e:
                logger.error(f"恢复槽位异常: {e}")

    # 否则挑选首个可用空闲槽位
    for s in slots:
        if not s.get("is_processing", False):
            return s["id"]
    return 0


async def save_slot_snapshot(slot_id: int, session_filename: str):
    """异步保存槽位到 NVMe 并登记 FIFO"""
    try:
        t0 = time.time()
        resp = await client.post(
            f"/slots/{slot_id}?action=save",
            json={"filename": session_filename}
        )
        cost_ms = (time.time() - t0) * 1000
        if resp.status_code == 200:
            await fifo_mgr.record_session(session_filename)
            logger.info(f"💾 [NVMe 存盘快照] 会话 {session_filename} 已存盘至 NVMe SSD (Slot {slot_id})，耗时 {cost_ms:.1f}ms")
    except Exception as e:
        logger.error(f"存盘异常: {e}")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    session_id = extract_session_id(body, dict(request.headers))
    session_filename = f"{session_id}.bin"
    is_stream = body.get("stream", False)

    # 1. 检查并按需秒级还原 NVMe 槽位
    slot_id = await get_target_slot(session_filename)
    if slot_id is None:
        slot_id = 0

    # 2. 转发请求给底层 llama-server
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length"]}

    if is_stream:
        req = client.build_request(
            "POST",
            "/v1/chat/completions",
            json=body,
            headers=headers,
            timeout=300.0
        )
        backend_resp = await client.send(req, stream=True)
        if backend_resp.status_code != 200:
            error_content = await backend_resp.aread()
            await backend_resp.aclose()
            return Response(
                content=error_content,
                status_code=backend_resp.status_code,
                media_type=backend_resp.headers.get("content-type", "application/json")
            )

        async def stream_generator():
            try:
                async for chunk in backend_resp.aiter_bytes():
                    yield chunk
            finally:
                await backend_resp.aclose()
                # 流式生成完毕后，异步存盘
                asyncio.create_task(save_slot_snapshot(slot_id, session_filename))

        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    else:
        resp = await client.post("/v1/chat/completions", json=body, headers=headers, timeout=300.0)
        # 非流式生成完毕后，异步存盘
        asyncio.create_task(save_slot_snapshot(slot_id, session_filename))
        return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))


# -----------------------------------------------------------------------------
# 透传所有其他接口 (GET/POST /v1/models, /health, /slots, /props 等)
# -----------------------------------------------------------------------------
@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"])
async def passthrough(request: Request, full_path: str):
    method = request.method
    url = f"/{full_path}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length"]}
    body = await request.body()
    params = dict(request.query_params)

    resp = await client.request(
        method=method,
        url=url,
        headers=headers,
        params=params,
        content=body,
        timeout=60.0
    )
    return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))


if __name__ == "__main__":
    logger.info(f"🚀 启动 Qwen3.8 Flash-Next 500 会话 FIFO 智能调度代理...")
    logger.info(f"客户端接入端口: 0.0.0.0:{PROXY_PORT}")
    logger.info(f"后端引擎直连: {BACKEND_URL}")
    logger.info(f"NVMe 缓存路径: {SLOT_CACHE_DIR} (FIFO 留存上限: {MAX_SESSIONS} 个会话)")
    uvicorn.run(app, host=PROXY_HOST, port=PROXY_PORT, log_level="warning")
