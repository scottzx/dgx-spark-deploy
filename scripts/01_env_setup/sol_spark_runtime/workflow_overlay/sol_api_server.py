#!/usr/bin/env python3
"""Sol-H3-Spark Resident FastAPI Server on NVIDIA DGX Spark (GB10).

Keeps MiniMax-H3 W8A8 (Stage 1), LTX-2.5 22B (Stage 2), and Qwen-VL NVFP4
permanently resident in GPU memory after a single initial warmup.
All subsequent video generation requests execute immediately in ~65s without warmup.
"""

import asyncio
from contextlib import asynccontextmanager
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import List, Literal, Optional

runtime = Path("/home/admin/sol-spark-runtime")
package = Path("/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark")
sys.path.insert(0, str(package))

# Global environment variables for CUDA, Triton, and offline models
os.environ["SOL_H3_SPARK_RUNTIME_ROOT"] = str(runtime)
os.environ["SOL_H3_SPARK_QWEN_IMAGE"] = "sol-h3-spark-qwen"
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
os.environ["CUDA_HOME"] = "/usr/local/cuda"
os.environ["CPATH"] = f"{runtime}/sysroot/usr/include/python3.12:{runtime}/sysroot/usr/include" + (
    f":{os.environ['CPATH']}" if "CPATH" in os.environ else ""
)
os.environ["PATH"] = f"/home/admin/.local/bin:/usr/local/cuda/bin:{os.environ.get('PATH', '')}"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["PYTHONUNBUFFERED"] = "1"
os.environ["TORCHINDUCTOR_COMPILE_THREADS"] = "1"
os.environ["TORCHINDUCTOR_MAX_AUTOTUNE"] = "0"

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from runtime.config import load_paths, normalize_case
from runtime.duration_profiles import DEFAULT_DURATION_S, validate_duration_s
from runtime.pipeline import Pipeline
from runtime.workflows import concatenate_clips

ffmpeg_bin = "/home/admin/.local/bin/ffmpeg"
out_root = runtime / "outputs" / "api_server_runs"
out_root.mkdir(parents=True, exist_ok=True)
upload_dir = runtime / "inputs" / "uploads"
upload_dir.mkdir(parents=True, exist_ok=True)

# Global pipeline instance and lock
pipeline_instance: Optional[Pipeline] = None
pipeline_lock = asyncio.Lock()
server_state = {
    "status": "STARTING",
    "startup_and_warmup_s": None,
    "ready_time": None,
    "total_requests_served": 0
}

# Boot task selected by env so fl2va and ref2va share one server file.
# SOL_TASK=fl2va|ref2va (default fl2va)
# SOL_PATHS_FILE=paths.json|paths.ref2va.json (default paths.json)
BOOT_TASK = os.environ.get("SOL_TASK", "fl2va").strip().lower()
BOOT_PATHS = Path(os.environ.get("SOL_PATHS_FILE", str(runtime / "paths.json"))).expanduser()
if not BOOT_PATHS.is_absolute():
    BOOT_PATHS = runtime / BOOT_PATHS
if BOOT_TASK not in ("fl2va", "ref2va", "t2va"):
    raise SystemExit(f"Unsupported SOL_TASK={BOOT_TASK}")
server_state["task"] = BOOT_TASK
server_state["paths_file"] = str(BOOT_PATHS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline_instance
    print(f"[Server] Initializing Sol-H3-Spark resident pipeline task={BOOT_TASK} paths={BOOT_PATHS}...", flush=True)
    paths = load_paths(BOOT_PATHS, task=BOOT_TASK)
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    server_dir = out_root / f"session_{timestamp}_{BOOT_TASK}"
    # server_dir is created by Pipeline.__init__

    pipeline_instance = Pipeline(paths, server_dir, task=BOOT_TASK)

    warmup_image = runtime / "inputs" / "yellow_cow_16x9.png"
    ref_id = runtime / "inputs" / "ep01_highlight" / "char_pack" / "id_front.jpg"
    if BOOT_TASK == "ref2va":
        ref_path = ref_id if ref_id.is_file() else warmup_image
        warmup_case = {
            "case_id": "server_warmup",
            "task": "ref2va",
            "seed": 999,
            "references": [{"type": "image", "path": str(ref_path)}],
            "prompt": "integrated_multimodal_description: A person standing outdoors in soft daylight, matching the reference identity. overall_soundscape: Quiet nature breeze. non_diegetic_music: None."
        }
    else:
        warmup_case = {
            "case_id": "server_warmup",
            "task": BOOT_TASK,
            "seed": 999,
            "first_frame": str(warmup_image) if warmup_image.is_file() else None,
            "prompt": "integrated_multimodal_description: A 3D animated character in a sunny field. overall_soundscape: Quiet nature breeze. non_diegetic_music: None."
        }
    norm_warmup = normalize_case(warmup_case, base_dir=runtime)

    print("[Server] Running one-time startup and warmup (FP8 quantization & JIT graph capture)...", flush=True)
    t0 = time.time()

    # Run warmup synchronously
    pipeline_instance.start(norm_warmup)
    elapsed = time.time() - t0

    server_state["status"] = "READY"
    server_state["startup_and_warmup_s"] = elapsed
    server_state["ready_time"] = datetime.datetime.now().isoformat()
    print(f"[Server] Sol-H3-Spark Pipeline ({BOOT_TASK}) is READY in {elapsed:.2f}s (~{elapsed/60:.1f}m)! Listening on port 8090...", flush=True)

    yield

    print("[Server] Shutting down pipeline and releasing GPU memory...", flush=True)
    if pipeline_instance is not None:
        pipeline_instance.close()
    server_state["status"] = "STOPPED"
    print("[Server] Shutdown complete.", flush=True)

app = FastAPI(
    title="Sol-H3-Spark Resident Video Generation API",
    description="Single-DGX-Spark GB10 persistent video inference server (65s / 5s 768p video)",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static outputs for direct HTTP video streaming and downloads
app.mount("/outputs", StaticFiles(directory=str(runtime / "outputs")), name="outputs")
app.mount("/inputs", StaticFiles(directory=str(runtime / "inputs")), name="inputs")


class ReferenceItem(BaseModel):
    type: Literal["image", "video", "audio"] = Field(..., description="Reference media type")
    path: str = Field(..., description="Absolute path or filename under inputs/")


class GenerateRequest(BaseModel):
    transition: Literal["independent", "continue"] = "independent"
    previous_clip_id: Optional[str] = None
    context_frames: Literal[5, 22, 39, 56] = 22
    audio_context_frames: int = 24
    prompt: str = Field(..., description="MiniMax-H3 prompt, including overall_soundscape and non_diegetic_music")
    first_frame: Optional[str] = Field(None, description="Absolute path or filename under inputs/ for FL2VA conditioning")
    last_frame: Optional[str] = Field(None, description="Absolute path or filename under inputs/ for FL2VA last-frame conditioning")
    references: Optional[List[ReferenceItem]] = Field(
        None,
        description="Ref2VA references (max 9 image / 3 video / 3 audio). Mutually exclusive with first/last frame.",
    )
    seed: int = Field(42, description="Random seed")
    case_id: Optional[str] = Field(None, description="Custom ID for output directory naming")
    mode: Literal["draft", "final"] = Field(
        "final",
        description="draft=Stage1+TAEH3 ~384p preview; final=full 768p. capture_dir+final refines draft.",
    )
    capture_dir: Optional[str] = Field(
        None,
        description="Existing Stage1 capture directory from a draft run; only with mode=final",
    )
    duration_s: int = Field(
        DEFAULT_DURATION_S,
        description="Clip duration seconds: 5 (default, 124->121) or 10 (243->241). No 15/20/30.",
    )


class ShotItem(BaseModel):
    transition: Optional[Literal["independent", "continue"]] = None
    first_frame: Optional[str] = None
    last_frame: Optional[str] = None
    duration_s: Literal[5, 10] = 5
    context_frames: Literal[5, 22, 39, 56] = 22
    audio_context_frames: int = 24
    shot_id: str = Field(..., description="ID for this shot, e.g. shot1_dilemma")
    prompt: str = Field(..., description="Prompt for this shot")
    audio_path: Optional[str] = Field(None, description="Optional path to TTS audio AAC file for voiceover muxing")
    seed: int = Field(42, description="Random seed for this shot")


class StoryRequest(BaseModel):
    story_id: str = Field("cow_story", description="Identifier for the story series")
    initial_frame: str = Field(..., description="Initial 16:9 canvas image path for Shot 1")
    shots: List[ShotItem] = Field(..., description="List of consecutive shots to chain together")
    mode: Literal["draft", "final"] = Field(
        "final",
        description="draft or final for every shot in this story request",
    )


@app.get("/health")
@app.get("/api/status")
async def get_status():
    return {
        "status": server_state["status"],
        "task": server_state.get("task", BOOT_TASK),
        "paths_file": server_state.get("paths_file", str(BOOT_PATHS)),
        "startup_and_warmup_s": server_state["startup_and_warmup_s"],
        "ready_time": server_state["ready_time"],
        "requests_served": server_state["total_requests_served"],
        "workflows": ["independent", "continue"],
        "device": "NVIDIA DGX Spark GB10 (128GB Unified Memory)",
        "model": f"MiniMax-H3 W8A8 DiT + LTX-2.5 22B Refiner (task={server_state.get('task', BOOT_TASK)}; modes: draft|final)"
    }


def _resolve_media_path(value: str, label: str) -> str:
    if Path(value).is_file():
        return value
    cand = runtime / "inputs" / value
    if cand.is_file():
        return str(cand)
    raise HTTPException(status_code=400, detail=f"{label} not found: {value}")


@app.post("/api/generate")
async def generate_single_video(req: GenerateRequest):
    if server_state["status"] != "READY":
        raise HTTPException(status_code=503, detail=f"Pipeline is not ready (current status: {server_state['status']})")

    async with pipeline_lock:
        try:
            duration_s = validate_duration_s(getattr(req, "duration_s", DEFAULT_DURATION_S))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        cid = req.case_id or f"gen_{int(time.time()*1000)}"
        pipe_task = pipeline_instance.task
        refs = req.references or []
        ff = req.first_frame
        lf = req.last_frame

        if pipe_task == "ref2va":
            if ff or lf:
                raise HTTPException(status_code=400, detail="ref2va pipeline rejects first_frame/last_frame; use references")
            if not refs:
                raise HTTPException(status_code=400, detail="ref2va requires references (at least one image or video)")
            resolved_refs = []
            for item in refs:
                resolved_refs.append({"type": item.type, "path": _resolve_media_path(item.path, "reference")})
            raw_case = {
                "case_id": cid,
                "task": "ref2va",
                "seed": req.seed,
                "references": resolved_refs,
                "prompt": req.prompt,
                "mode": req.mode,
                "capture_dir": req.capture_dir,
                "duration_s": duration_s,
            }
        else:
            if refs:
                raise HTTPException(status_code=400, detail=f"{pipe_task} pipeline rejects references; use first_frame/last_frame")
            if ff:
                ff = _resolve_media_path(ff, "first_frame")
            if lf:
                lf = _resolve_media_path(lf, "last_frame")
            raw_case = {
                "case_id": cid,
                "task": "fl2va" if (ff or lf or req.transition == "continue") else "t2va",
                "seed": req.seed,
                "first_frame": ff,
                "prompt": req.prompt,
                "mode": req.mode,
                "capture_dir": req.capture_dir,
                "duration_s": duration_s,
            }
            if lf:
                raw_case["last_frame"] = lf

        if req.transition == "continue" and req.capture_dir:
            raise HTTPException(status_code=400, detail="continue cannot use capture_dir")
        raw_case.update(transition=req.transition, previous_clip_id=req.previous_clip_id,
            context_frames=req.context_frames, audio_context_frames=req.audio_context_frames)

        if getattr(req, "mode", "final") == "final" and getattr(req, "capture_dir", None):
            cap = Path(req.capture_dir)
            if not cap.is_dir():
                raise HTTPException(status_code=400, detail=f"capture_dir not found: {req.capture_dir}")
            raw_case = {
                "case_id": cid,
                "task": pipeline_instance.task,
                "seed": req.seed,
                "prompt": req.prompt or "refine_only",
                "capture_dir": str(cap.resolve()),
                "mode": "final",
                "duration_s": duration_s,
            }
            norm_case = raw_case
        else:
            if pipe_task == "ref2va" and raw_case.get("task") != "ref2va":
                raise HTTPException(status_code=400, detail=f"request task={raw_case.get('task')} incompatible with booted pipeline task={pipe_task}")
            try:
                norm_case = normalize_case(raw_case, base_dir=runtime)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if norm_case["task"] != pipe_task:
                raise HTTPException(status_code=400, detail=f"normalized task={norm_case['task']} != pipeline task={pipe_task}")
            norm_case["mode"] = req.mode
            norm_case["duration_s"] = duration_s

        norm_case["duration_s"] = duration_s
        t0 = time.time()
        try:
            res = await asyncio.to_thread(pipeline_instance.generate, norm_case, mode=req.mode)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        elapsed = time.time() - t0
        server_state["total_requests_served"] += 1

        vid_path = Path(res["output"])
        rel_path = vid_path.relative_to(runtime / "outputs")

        # Generate contact sheet from the actual delivered timeline.
        val_dir = vid_path.parent / "contact_sheet"
        val_dir.mkdir(parents=True, exist_ok=True)
        cs_file = val_dir / "contact_sheet.png"
        frames = res.get("delivered_frames", 241 if duration_s == 10 else 121)
        positions = sorted(set(round(i * (frames - 1) / 5) for i in range(6)))
        vf = "select='" + "+".join(f"eq(n\\,{n})" for n in positions) + "',scale=448:256,tile=3x2"
        subprocess.run([
            ffmpeg_bin, "-y", "-i", str(vid_path),
            "-vf", vf,
            "-frames:v", "1", str(cs_file)
        ], check=True)

        return {
            "status": "PASS",
            "case_id": cid,
            "mode": getattr(req, "mode", "final"),
            "duration_s": duration_s,
            "e2e_s": round(elapsed, 2),
            "transition": res["transition"],
            "previous_clip_id": res.get("previous_clip_id"),
            "delivered_frames": res["delivered_frames"],
            "delivered_duration_s": res["delivered_duration_s"],
            "trim_frames": res["trim_frames"],
            "continuation": res.get("continuation"),
            "reported_e2e_s": round(res.get("e2e_s", 0), 2),
            "qwen_s": res.get("qwen_s"),
            "stage1_s": res.get("stage1_s"),
            "stage2_s": res.get("stage2_s"),
            "capture_dir": res.get("capture_dir"),
            "video_path": str(vid_path),
            "video_url": f"/outputs/{rel_path}",
            "contact_sheet_url": f"/outputs/{cs_file.relative_to(runtime / 'outputs')}"
        }


@app.post("/api/story")
async def generate_chained_story(req: StoryRequest):
    if server_state["status"] != "READY":
        raise HTTPException(status_code=503, detail="Pipeline is not READY")
    if pipeline_instance.task != "fl2va":
        raise HTTPException(status_code=400, detail="Story workflows require fl2va")
    if not req.shots or not all(s.shot_id.replace('_', '').replace('-', '').isalnum() for s in req.shots):
        raise HTTPException(status_code=400, detail="Provide shots with file-safe shot_id values")
    if not req.story_id.replace('_', '').replace('-', '').isalnum():
        raise HTTPException(status_code=400, detail="story_id must be file-safe")
    initial = _resolve_media_path(req.initial_frame, "initial_frame")
    async with pipeline_lock:
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        story_dir = out_root / f"{req.story_id}_{timestamp}"
        story_dir.mkdir(parents=True, exist_ok=False)
        rows, clips = [], []
        previous_id, legacy_frame = None, initial
        for i, shot in enumerate(req.shots):
            cid = f"{req.story_id}_{timestamp}_{shot.shot_id}_{i+1}"
            # Omitted transition preserves the old single-tail-frame story API.
            transition = shot.transition or "independent"
            case = dict(case_id=cid, task="fl2va", seed=shot.seed, prompt=shot.prompt,
                duration_s=shot.duration_s, transition=transition)
            if transition == "continue":
                case.update(previous_clip_id=previous_id, context_frames=shot.context_frames,
                    audio_context_frames=shot.audio_context_frames)
            else:
                case["first_frame"] = _resolve_media_path(shot.first_frame, "first_frame") if shot.first_frame else (
                    legacy_frame if shot.transition is None else initial)
            if shot.last_frame:
                case["last_frame"] = _resolve_media_path(shot.last_frame, "last_frame")
            try:
                normalized = normalize_case(case, base_dir=runtime)
                row = await asyncio.to_thread(pipeline_instance.generate, normalized, mode=req.mode)
            except (ValueError, FileNotFoundError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            server_state["total_requests_served"] += 1
            previous_id = cid
            legacy_frame = str(story_dir / f"{cid}_tail.png")
            subprocess.run([ffmpeg_bin, "-y", "-i", row["output"], "-vf",
                f"select=eq(n\\,{row['delivered_frames']-1})", "-frames:v", "1", legacy_frame], check=True)
            clip = row["output"]
            if shot.audio_path:
                audio = _resolve_media_path(shot.audio_path, "audio_path")
                clip = str(story_dir / f"{cid}_voiced.mp4")
                subprocess.run([ffmpeg_bin, "-y", "-i", row["output"], "-i", audio,
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
                    "-ar", "32000", "-ac", "2", "-af", "apad", "-t", str(row["delivered_duration_s"]), clip], check=True)
            rows.append(row)
            clips.append(clip)
        concat = story_dir / "concat.txt"
        concat.write_text("".join(f"file '{Path(c).resolve()}'\n" for c in clips))
        master = story_dir / "master.mp4"
        await asyncio.to_thread(concatenate_clips, clips,
            [r["delivered_frames"] for r in rows], master)
        report = dict(status="PASS", story_id=req.story_id, shots=rows,
            video_path=str(master), video_url="/outputs/"+str(master.relative_to(runtime/'outputs')),
            delivered_frames=sum(r["delivered_frames"] for r in rows))
        (story_dir / "story_result.json").write_text(json.dumps(report, indent=2)+"\n")
        return report


@app.post("/api/upload")
async def upload_asset(file: UploadFile = File(...)):
    dest = upload_dir / file.filename
    with open(dest, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {
        "status": "UPLOADED",
        "filename": file.filename,
        "local_path": str(dest),
        "url": f"/inputs/uploads/{file.filename}"
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090, access_log=True)
