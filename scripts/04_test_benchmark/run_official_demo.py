import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

runtime = Path("/home/admin/sol-spark-runtime")
timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
out = runtime / "outputs" / f"official_demo_{timestamp}"
batch_file = runtime / f"official_demo_batch_{timestamp}.jsonl"

cases = [
    {
        "case_id": "jazz_singer",
        "task": "t2va",
        "seed": 42,
        "prompt": "A charismatic jazz singer in a midnight-blue satin gown walks from a dim backstage corridor through heavy burgundy curtains and onto a luminous 1930s Art Deco theater stage. The camera follows her in one fluid tracking shot as she approaches a chrome microphone, the warm spotlight rises, and the seated audience emerges softly through blue haze. She takes a breath, places one hand on the microphone stand, and begins the first note. Preserve her face, gown, hairstyle, and the theater layout throughout. Photorealistic skin, satin and chrome textures, expressive but controlled movement, elegant amber and cobalt lighting, cinematic shallow depth of field, no cuts, no text."
    },
    {
        "case_id": "mountain_lake",
        "task": "t2va",
        "seed": 42,
        "prompt": "integrated_multimodal_description: A wide aerial shot follows an eagle gliding over a turquoise alpine lake, with pine forest, a narrow waterfall and snow-covered peaks visible in the background. Its wings flex gently as it banks through the warm afternoon light. The camera maintains its distance and reveals the landscape in one continuous five-second shot. Natural colors, realistic feathers, no cuts or text. overall_soundscape: Wind moving through the valley, a distant eagle call and soft waterfall noise. non_diegetic_music: None."
    },
    {
        "case_id": "snow_leopard",
        "task": "t2va",
        "seed": 42,
        "prompt": "integrated_multimodal_description: [Shot 1] Photoreal wildlife documentary in crisp mountain daylight, a medium-wide view frames one majestic snow leopard with thick spotted fur moving across a jagged, snow-covered ridge beneath towering Himalayan peaks and a clear blue sky. During one continuous five-second shot, the camera pans slowly to follow its low stalking gait as each paw sinks slightly into fresh powder. The leopard pauses near the end, its long bushy tail twitching for balance while its green eyes scan the valley; frost-dusted whiskers and individual hairs remain sharply visible. Preserve the animal's anatomy, markings, scale, paw contact, and ridge geometry throughout, with no cuts, text, or logos. overall_soundscape: Soft mountain wind passes over the ridge while paws compress fresh snow with muted crunches. A faint tail brush and the leopard's quiet breathing are audible in the cold open air. non_diegetic_music: N/A"
    }
]

with open(batch_file, "w", encoding="utf-8") as f:
    for c in cases:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")

print(f"Prepared official demo batch prompt file ({len(cases)} cases): {batch_file}", flush=True)

env = os.environ.copy()
old_path = env.get("PATH", "")
env["PATH"] = "/home/admin/.local/bin:/usr/local/cuda/bin:" + old_path

cmd = [
    "bash",
    "/home/admin/switch_to_minimax.sh",
    "--prompts",
    str(batch_file),
    "--output-dir",
    str(out)
]
print(f"Starting Sol-H3-Spark official demo batch generation to {out}...", flush=True)
subprocess.run(cmd, check=True, env=env)

print("Batch generation finished! Extracting contact sheets & validating videos...", flush=True)
results_file = out / "results.json"
if results_file.exists():
    results = json.loads(results_file.read_text())
    for row in results.get("requests", []):
        cid = row["case_id"]
        vid = row["output"]
        val_dir = out / "validation" / cid
        subprocess.run([
            str(runtime / "bootstrap-env/bin/python"),
            str(runtime / "verify_sol_h3_video.py"),
            vid,
            "--output-dir",
            str(val_dir)
        ], check=True, env=env)
        print(f"Validated and generated contact sheet for {cid} (E2E: {row.get('e2e_s'):.2f}s)", flush=True)

print("OFFICIAL_DEMO_BATCH_COMPLETED_SUCCESSFULLY", out, flush=True)
