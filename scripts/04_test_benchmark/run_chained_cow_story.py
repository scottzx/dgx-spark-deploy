#!/usr/bin/env python3
"""Run chained FL2VA video generation for a 20-second multi-shot story on DGX Spark."""

import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

runtime = Path("/home/admin/sol-spark-runtime")
package = Path("/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark")
sys.path.insert(0, str(package))

# Setup environment variables required by Triton, CUDA, and Docker wrapper
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

# Prevent PyTorch Inductor multi-worker fork deadlocks in multithreaded FastVideo runtime
os.environ["TORCHINDUCTOR_COMPILE_THREADS"] = "1"
os.environ["TORCHINDUCTOR_MAX_AUTOTUNE"] = "0"

from runtime.config import load_paths, normalize_case
from runtime.pipeline import Pipeline

ffmpeg_bin = "/home/admin/.local/bin/ffmpeg"
timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
out_dir = runtime / "outputs" / f"cow_story_20s_{timestamp}"

initial_image = runtime / "inputs" / "yellow_cow_16x9.png"
if not initial_image.is_file():
    raise FileNotFoundError(f"Missing initial 16:9 canvas: {initial_image}")

shot_definitions = [
    {
        "case_id": "shot1_dilemma",
        "prompt": "integrated_multimodal_description: [Shot 1] A 3D stylized animated scene of a yellow cow character with curved gray horns and white hooves. In one continuous five-second shot, the camera slowly pushes in on the yellow cow. From 0.0 to 2.5 seconds, he blinks, gestures with his white hands in mild frustration, shaking his head at the blackboard. From 2.5 to 5.0 seconds, he turns his head to face the viewer with curious engaging eyes. Coherent character anatomy, horns, yellow body and blurred green background throughout, no cuts, no text. overall_soundscape: Quiet outdoor ambiance with gentle rustling leaves and soft character breath. non_diegetic_music: None.",
        "tts_audio": runtime / "inputs" / "shot_1.aac",
    },
    {
        "case_id": "shot2_question",
        "prompt": "integrated_multimodal_description: [Shot 2] The same 3D stylized yellow cow character in medium close-up. In one continuous five-second shot, the camera stays steady. From 0.0 to 2.5 seconds, the yellow cow tilts his head slightly, raises his right hand to pose an intriguing question, his mouth moving as if speaking. From 2.5 to 5.0 seconds, his expression becomes hopeful and curious as he lowers his hand. Consistent yellow body, gray horns and facial features throughout, no cuts, no text. overall_soundscape: Soft mountain breeze, subtle clothing rustle and quiet character vocalization. non_diegetic_music: None.",
        "tts_audio": runtime / "inputs" / "shot_2.aac",
    },
    {
        "case_id": "shot3_breakthrough",
        "prompt": "integrated_multimodal_description: [Shot 3] The same 3D stylized yellow cow character stands with great confidence. In one continuous five-second shot, warm light brightens the scene. From 0.0 to 2.5 seconds, the yellow cow breaks into a bright cheerful smile, his eyes widening with excitement as he opens both arms in a welcoming gesture. From 2.5 to 5.0 seconds, he nods enthusiastically to reveal a technological breakthrough. Coherent character anatomy, yellow body, horns and lighting throughout, no cuts, no text. overall_soundscape: Crisp outdoor air, cheerful uplifting character breath and subtle rustle. non_diegetic_music: None.",
        "tts_audio": runtime / "inputs" / "shot_3.aac",
    },
    {
        "case_id": "shot4_demonstration",
        "prompt": "integrated_multimodal_description: [Shot 4] The same 3D stylized yellow cow character completes the presentation. In one continuous five-second shot, the camera slowly pulls back. From 0.0 to 2.5 seconds, the yellow cow points forward enthusiastically with his white hand, nodding repeatedly with pride and joy. From 2.5 to 5.0 seconds, he rests both hands comfortably, beaming at the camera with a satisfied smile. Smooth character motion, consistent anatomy and environment throughout, no cuts, no text. overall_soundscape: Soft valley wind, gentle movement sounds and peaceful nature tone. non_diegetic_music: None.",
        "tts_audio": runtime / "inputs" / "shot_4.aac",
    },
]

print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] === Starting Chained FL2VA Cow Story Generation ({len(shot_definitions)} shots, 20s total) ===", flush=True)
print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Output directory: {out_dir}", flush=True)

paths = load_paths(runtime / "paths.json", task="fl2va")
pipeline = Pipeline(paths, out_dir, task="fl2va")

case0 = {
    "case_id": shot_definitions[0]["case_id"],
    "task": "fl2va",
    "seed": 42,
    "first_frame": str(initial_image),
    "prompt": shot_definitions[0]["prompt"]
}
normalized_c0 = normalize_case(case0, base_dir=runtime)

print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Starting pipeline and executing warmup (approx. 5-6 mins for FP8 conversion & JIT compilation)...", flush=True)
warmup_start = time.time()
pipeline.start(normalized_c0)
warmup_elapsed = time.time() - warmup_start
print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Pipeline is READY! Warmup completed in {warmup_elapsed:.2f}s (~{warmup_elapsed/60:.1f}m)", flush=True)

current_first_frame = str(initial_image)
voiced_shots = []

try:
    for idx, shot in enumerate(shot_definitions):
        cid = shot["case_id"]
        print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] --- [Shot {idx+1}/4] Generating {cid} with first_frame: {Path(current_first_frame).name} ---", flush=True)
        raw_case = {
            "case_id": cid,
            "task": "fl2va",
            "seed": 42,
            "first_frame": current_first_frame,
            "prompt": shot["prompt"]
        }
        norm_case = normalize_case(raw_case, base_dir=runtime)
        t0 = time.time()
        res = pipeline.generate(norm_case)
        elapsed = time.time() - t0
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] PASS: {cid} generated in {elapsed:.2f}s (reported e2e: {res['e2e_s']:.2f}s)! Video: {res['output']}", flush=True)

        vid_path = Path(res["output"])
        val_dir = out_dir / "validation" / cid
        val_dir.mkdir(parents=True, exist_ok=True)

        # 1. Run validation and extract contact sheet
        subprocess.run([
            str(runtime / "bootstrap-env/bin/python"),
            str(runtime / "verify_sol_h3_video.py"),
            str(vid_path),
            "--output-dir",
            str(val_dir)
        ], check=True)

        # 2. Extract tail frame (last frame) as next shot's first_frame
        tail_frame = val_dir / "tail_frame.png"
        subprocess.run([
            ffmpeg_bin, "-y", "-sseof", "-0.1", "-i", str(vid_path),
            "-update", "1", "-vframes", "1", str(tail_frame)
        ], check=True)
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Extracted tail frame for chaining: {tail_frame}", flush=True)
        current_first_frame = str(tail_frame)

        # 3. Mux TTS voiceover into this shot
        tts_file = shot["tts_audio"]
        voiced_mp4 = out_dir / f"{cid}_voiced.mp4"
        if tts_file.is_file():
            subprocess.run([
                ffmpeg_bin, "-y", "-i", str(vid_path), "-i", str(tts_file),
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-map", "0:v:0", "-map", "1:a:0", "-shortest",
                str(voiced_mp4)
            ], check=True)
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Muxed TTS voiceover into: {voiced_mp4}", flush=True)
            voiced_shots.append(voiced_mp4)
        else:
            voiced_shots.append(vid_path)

    pipeline.finish()
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] Mean E2E across formal requests: {pipeline.report['mean_e2e_s']:.2f}s", flush=True)
finally:
    pipeline.close()

# 4. Concatenate all 4 shots into the final 20s master video
concat_txt = out_dir / "concat_list.txt"
with open(concat_txt, "w") as f:
    for p in voiced_shots:
        f.write(f"file '{p.resolve()}'\n")

master_mp4 = out_dir / f"yellow_cow_20s_master.mp4"
print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Concatenating {len(voiced_shots)} shots into {master_mp4}...", flush=True)
subprocess.run([
    ffmpeg_bin, "-y", "-f", "concat", "-safe", "0",
    "-i", str(concat_txt),
    "-c", "copy",
    str(master_mp4)
], check=True)

# Also create contact sheet for the master video
master_val_dir = out_dir / "validation" / "master_20s"
master_val_dir.mkdir(parents=True, exist_ok=True)
subprocess.run([
    ffmpeg_bin, "-y", "-i", str(master_mp4),
    "-vf", r"select='not(mod(n\,60))',scale=448:256,tile=4x2",
    "-frames:v", "1",
    str(master_val_dir / "master_contact_sheet.png")
], check=True)

print(f"\n==========================================================", flush=True)
print(f"🎉 MASTER 20-SECOND VIDEO GENERATED SUCCESSFULLY!", flush=True)
print(f"Output: {master_mp4}", flush=True)
print(f"Contact Sheet: {master_val_dir / 'master_contact_sheet.png'}", flush=True)
print(f"==========================================================", flush=True)
