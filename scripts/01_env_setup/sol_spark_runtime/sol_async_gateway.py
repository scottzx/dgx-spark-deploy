#!/usr/bin/env python3
"""Unified Async AI Hub & Gateway for DGX Spark & MiniMax.

1. Video: Dispatches async video tasks to local Sol-H3-Spark (GB10 GPU resident) at port 8090.
2. Text / LLM: Proxies OpenAI-compatible chat completions to MiniMax-Text-01 (with streaming SSE).
3. Image: Translates /images/generations to MiniMax image-01.
4. Voice / TTS: Translates text-to-voice to MiniMax speech-01-turbo.
"""

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
import time
import urllib.request
import uuid
from typing import Dict, Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sol_async_gateway")

runtime = Path("/home/admin/sol-spark-runtime")
upload_dir = runtime / "inputs" / "uploads"
upload_dir.mkdir(parents=True, exist_ok=True)
tasks_dir = runtime / "outputs" / "async_tasks"
tasks_dir.mkdir(parents=True, exist_ok=True)
tts_dir = runtime / "outputs" / "tts"
tts_dir.mkdir(parents=True, exist_ok=True)

LOCAL_SPARK_URL = "http://127.0.0.1:8090"
PUBLIC_SPARK_HOST = "http://100.115.178.96:8090"
DEFAULT_FALLBACK_IMAGE = str(runtime / "inputs" / "yellow_cow_16x9.png")
MINIMAX_API_HOST = "https://api.minimax.chat"

app = FastAPI(
    title="DGX Spark Unified AI Hub (Sol-H3 + MiniMax)",
    description="Unified Gateway for Local DGX Spark Video & MiniMax Text/Image/Voice",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tasks_db: Dict[str, Dict[str, Any]] = {}
task_queue = asyncio.Queue()

def save_task_to_disk(task_id: str, data: dict):
    try:
        path = tasks_dir / f"{task_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to persist task {task_id} to disk: {e}")

async def worker_loop():
    logger.info("Starting background Sol-H3 video generation worker...")
    while True:
        task_id = await task_queue.get()
        task = tasks_db.get(task_id)
        if not task:
            task_queue.task_done()
            continue

        try:
            task["status"] = "running"
            save_task_to_disk(task_id, task)
            logger.info(f"Executing video generation task: {task_id}")

            prompt = task.get("prompt", "")
            first_frame_url = task.get("first_frame_url")
            seed = task.get("seed", 42)

            local_first_frame = None
            if first_frame_url:
                if first_frame_url.startswith("http://") or first_frame_url.startswith("https://"):
                    ext = ".png"
                    if ".jpg" in first_frame_url.lower() or ".jpeg" in first_frame_url.lower():
                        ext = ".jpg"
                    dl_dest = upload_dir / f"ff_{task_id}{ext}"
                    logger.info(f"Downloading first frame from {first_frame_url} -> {dl_dest}")
                    try:
                        urllib.request.urlretrieve(first_frame_url, str(dl_dest))
                        local_first_frame = str(dl_dest)
                    except Exception as dl_err:
                        logger.warning(f"Failed to download first frame: {dl_err}")
                elif Path(first_frame_url).is_file():
                    local_first_frame = first_frame_url

            # Ensure first_frame is present for fl2va task
            if not local_first_frame or not Path(local_first_frame).is_file():
                logger.info(f"No valid first frame, falling back to default: {DEFAULT_FALLBACK_IMAGE}")
                local_first_frame = DEFAULT_FALLBACK_IMAGE

            payload = {
                "prompt": prompt,
                "first_frame": local_first_frame,
                "seed": seed,
                "case_id": task_id
            }

            def run_sync_generate():
                t0 = time.time()
                v_url, c_url = "", ""
                try:
                    req = urllib.request.Request(
                        f"{LOCAL_SPARK_URL}/api/generate",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"}
                    )
                    with urllib.request.urlopen(req, timeout=300) as resp:
                        resp_data = json.loads(resp.read().decode("utf-8"))
                        v_url = resp_data.get("video_url", "")
                        c_url = resp_data.get("contact_sheet_url", "")
                except Exception as call_err:
                    logger.warning(f"Direct API call returned: {call_err}, checking disk for completed MP4...")
                    found = None
                    for cand in (runtime / "outputs" / "api_server_runs").glob(f"**/{task_id}/**/refined*.mp4"):
                        if cand.is_file() and cand.stat().st_size > 0:
                            found = cand
                            break
                    if found:
                        v_url = f"/outputs/{found.relative_to(runtime / "outputs")}"
                        logger.info(f"Recovered MP4 directly from disk: {v_url}")
                    else:
                        raise call_err
                return v_url, c_url, time.time() - t0

            video_rel_url, cs_rel_url, elapsed = await asyncio.to_thread(run_sync_generate)
            full_video_url = f"{PUBLIC_SPARK_HOST}{video_rel_url}" if video_rel_url else ""
            full_cs_url = f"{PUBLIC_SPARK_HOST}{cs_rel_url}" if cs_rel_url else ""

            task["status"] = "succeeded"
            task["elapsed_s"] = round(elapsed, 2)
            task["content"] = {
                "video_url": full_video_url,
                "contact_sheet_url": full_cs_url
            }
            logger.info(f"Task {task_id} completed successfully in {elapsed:.1f}s -> {full_video_url}")
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
            task["status"] = "failed"
            task["error"] = {"code": "GENERATION_ERROR", "message": str(e)}
        finally:
            save_task_to_disk(task_id, task)
            task_queue.task_done()

@app.on_event("startup")
async def startup_event():
    for f in tasks_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                if "id" in data:
                    tasks_db[data["id"]] = data
        except Exception:
            pass
    asyncio.create_task(worker_loop())

@app.get("/health")
async def health_check():
    try:
        with urllib.request.urlopen(f"{LOCAL_SPARK_URL}/health", timeout=3) as resp:
            spark_health = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        spark_health = {"error": str(e)}
    return {
        "gateway": "READY",
        "queue_size": task_queue.qsize(),
        "spark_pipeline": spark_health,
        "features": ["sol-h3-spark-video", "minimax-text-proxy", "minimax-image-proxy", "minimax-tts-proxy"]
    }

# =========================================================================
# Video Tasks (Ark & OpenAI Compatible Format)
# =========================================================================

@app.post("/contents/generations/tasks")
async def create_ark_task(request: Request):
    body = await request.json()
    task_id = f"spark_task_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
    
    prompt = ""
    first_frame_url = None
    
    content = body.get("content", [])
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text" or "text" in item:
                    prompt = item.get("text", prompt)
                if item.get("type") == "image_url" or "image_url" in item:
                    img_info = item.get("image_url", {})
                    if isinstance(img_info, dict):
                        first_frame_url = img_info.get("url")
                    elif isinstance(img_info, str):
                        first_frame_url = img_info
    
    if not prompt:
        prompt = body.get("prompt", "A high quality cinematic video")
    if not first_frame_url:
        first_frame_url = body.get("first_frame")
    
    seed = body.get("seed", 42)
    model = body.get("model", "sol-h3-spark")
    
    task_data = {
        "id": task_id,
        "model": model,
        "status": "queued",
        "prompt": prompt,
        "first_frame_url": first_frame_url,
        "seed": seed,
        "created_at": time.time()
    }
    tasks_db[task_id] = task_data
    save_task_to_disk(task_id, task_data)
    await task_queue.put(task_id)
    
    logger.info(f"Enqueued new video task {task_id} (model: {model}, queue: {task_queue.qsize()})")
    return {"id": task_id, "status": "queued"}

@app.get("/contents/generations/tasks/{task_id}")
async def query_ark_task(task_id: str):
    task = tasks_db.get(task_id)
    if not task:
        disk_path = tasks_dir / f"{task_id}.json"
        if disk_path.is_file():
            with open(disk_path, "r", encoding="utf-8") as fp:
                task = json.load(fp)
                tasks_db[task_id] = task
        else:
            raise HTTPException(status_code=404, detail="Task not found")
    
    status = task.get("status", "processing")
    resp: Dict[str, Any] = {
        "id": task_id,
        "model": task.get("model", "sol-h3-spark"),
        "status": status
    }
    if status == "succeeded":
        resp["content"] = task.get("content", {})
    elif status == "failed":
        resp["error"] = task.get("error", {"code": "TASK_FAILED", "message": "Unknown error"})
    return resp

@app.post("/api/v1/tasks")
async def create_v1_task(request: Request):
    return await create_ark_task(request)

@app.get("/api/v1/tasks/{task_id}")
async def query_v1_task(task_id: str):
    return await query_ark_task(task_id)

# =========================================================================
# Text / Chat Completions Proxy (MiniMax-Text-01)
# =========================================================================

def get_auth_header(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth:
        env_key = os.environ.get("MINIMAX_API_KEY", "")
        if env_key:
            auth = f"Bearer {env_key}"
    return auth

@app.post("/chat/completions")
@app.post("/v1/chat/completions")
async def proxy_chat_completions(request: Request):
    auth = get_auth_header(request)
    if not auth:
        raise HTTPException(status_code=401, detail="Missing Authorization Bearer token")

    body = await request.json()
    model = body.get("model", "MiniMax-Text-01")
    # Remap generic names to MiniMax-Text-01
    if not model or "minimax" not in model.lower():
        body["model"] = "MiniMax-Text-01"

    stream = body.get("stream", False)
    url = f"{MINIMAX_API_HOST}/v1/chat/completions"
    headers = {
        "Authorization": auth,
        "Content-Type": "application/json"
    }

    client = httpx.AsyncClient(timeout=180.0)

    if stream:
        async def stream_generator():
            try:
                async with client.stream("POST", url, headers=headers, json=body) as r:
                    async for chunk in r.aiter_bytes():
                        yield chunk
            finally:
                await client.aclose()

        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    else:
        try:
            r = await client.post(url, headers=headers, json=body)
            await client.aclose()
            return Response(content=r.content, status_code=r.status_code, media_type="application/json")
        except Exception as e:
            await client.aclose()
            raise HTTPException(status_code=502, detail=f"MiniMax upstream error: {str(e)}")

# =========================================================================
# Image Generation Proxy (MiniMax image-01)
# =========================================================================

@app.post("/images/generations")
@app.post("/v1/images/generations")
async def proxy_image_generations(request: Request):
    auth = get_auth_header(request)
    if not auth:
        raise HTTPException(status_code=401, detail="Missing Authorization Bearer token")

    body = await request.json()
    prompt = body.get("prompt", "")
    size = body.get("size", "1024x1024")
    
    # Map size to aspect ratio
    aspect_ratio = "1:1"
    if "1792x1024" in size or "1344x768" in size or "16:9" in size:
        aspect_ratio = "16:9"
    elif "1024x1792" in size or "768x1344" in size or "9:16" in size:
        aspect_ratio = "9:16"

    mm_body = {
        "model": "image-01",
        "prompt": prompt,
        "aspect_ratio": aspect_ratio
    }

    url = f"{MINIMAX_API_HOST}/v1/image_generation"
    headers = {
        "Authorization": auth,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            r = await client.post(url, headers=headers, json=mm_body)
            data = r.json()
            # MiniMax image response structure
            img_url = ""
            if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                img_url = data["data"][0].get("url", "")
            elif "output" in data and "image_url" in data["output"]:
                img_url = data["output"]["image_url"]
            elif "image_url" in data:
                img_url = data["image_url"]

            if not img_url:
                # Return original response if url not found
                return Response(content=r.content, status_code=r.status_code, media_type="application/json")

            # Return OpenAI standard image format
            return {
                "created": int(time.time()),
                "data": [{"url": img_url}]
            }
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"MiniMax image error: {str(e)}")

# =========================================================================
# Voice / TTS Proxy (MiniMax speech-01-turbo)
# =========================================================================

@app.post("/v1/text-to-voice/design")
@app.post("/v1/t2a_v2")
async def proxy_tts_generation(request: Request):
    auth = get_auth_header(request)
    if not auth:
        auth = request.headers.get("xi-api-key", "")
        if auth:
            auth = f"Bearer {auth}"
        else:
            raise HTTPException(status_code=401, detail="Missing API Key")

    body = await request.json()
    text = body.get("text", "") or body.get("prompt", "")
    voice_id = body.get("voice_id", "male-qn-qingse")
    model = body.get("model", "speech-01-turbo")

    mm_body = {
        "model": model,
        "text": text,
        "voice_setting": {
            "voice_id": voice_id,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 2
        }
    }

    url = f"{MINIMAX_API_HOST}/v1/t2a_v2"
    headers = {
        "Authorization": auth,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            r = await client.post(url, headers=headers, json=mm_body)
            data = r.json()
            
            # MiniMax returns hex audio or data
            audio_data_hex = data.get("data", {}).get("audio", "")
            if audio_data_hex:
                audio_bytes = bytes.fromhex(audio_data_hex)
                b64_audio = base64.b64encode(audio_bytes).decode("ascii")
                # Save to tts_dir
                audio_id = f"tts_{int(time.time()*1000)}"
                audio_path = tts_dir / f"{audio_id}.mp3"
                with open(audio_path, "wb") as af:
                    af.write(audio_bytes)

                return {
                    "text": text,
                    "previews": [{
                        "audio_base_64": b64_audio,
                        "generated_voice_id": voice_id,
                        "media_type": "audio/mpeg",
                        "duration_secs": round(len(audio_bytes) / 16000, 2),
                        "language": "zh"
                    }]
                }
            return Response(content=r.content, status_code=r.status_code, media_type="application/json")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"MiniMax TTS error: {str(e)}")

# =========================================================================
# Models Catalog Endpoint
# =========================================================================

@app.get("/v1/models")
@app.get("/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {"id": "sol-h3-spark", "object": "model", "type": "video", "owned_by": "dgx-spark"},
            {"id": "doubao-seedance-2-0-260128", "object": "model", "type": "video", "owned_by": "dgx-spark"},
            {"id": "doubao-seedance-2-5-260628", "object": "model", "type": "video", "owned_by": "dgx-spark"},
            {"id": "MiniMax-Text-01", "object": "model", "type": "llm", "owned_by": "minimax"},
            {"id": "abab6.5s-chat", "object": "model", "type": "llm", "owned_by": "minimax"},
            {"id": "image-01", "object": "model", "type": "image", "owned_by": "minimax"},
            {"id": "speech-01-turbo", "object": "model", "type": "voice", "owned_by": "minimax"}
        ]
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8095)
