import json
import os
from pathlib import Path
import subprocess

runtime = Path("/home/admin/sol-spark-runtime")
out = runtime / "outputs" / "pool_elbow_story_001"
batch_file = runtime / "pool_elbow_story_batch.jsonl"

cases = [
    {
        "case_id": "shot1_elbow_bump",
        "task": "t2va",
        "seed": 42,
        "prompt": "A cinematic medium shot by a sunny resort swimming pool. A 32-year-old Asian father with short neat black hair in dark navy swim trunks sits by the poolside stone deck. He accidentally bumped his elbow against the pool edge and winces slightly with a mild grimace, rubbing his elbow with his hand. Clear turquoise water ripples in sunlight, natural cinematic lighting, gentle water splashes and soft ambient sound."
    },
    {
        "case_id": "shot2_daughter_blows",
        "task": "t2va",
        "seed": 42,
        "prompt": "A heartwarming medium close-up shot by the swimming pool. A 32-year-old Asian father sits on the pool deck holding his bumped elbow. His adorable 3-year-old Asian daughter with cute double bun hair in a pink and yellow swimsuit crouches beside him. She gently holds his arm with both tiny hands, puffs her round cheeks and blows softly on his elbow to soothe the pain, saying pain-go-away. Clear turquoise water in background, tender family atmosphere, natural lighting, soft blowing sound and gentle water ripples."
    },
    {
        "case_id": "shot3_happy_laugh",
        "task": "t2va",
        "seed": 42,
        "prompt": "A heartwarming cinematic medium shot by the sunny swimming pool. The 32-year-old Asian father smiles warmly and bursts into joyous affectionate laughter, deeply cheered by his sweet daughter. He gently pats the 3-year-old daughter's cute double bun hair as she beams with delight. Warm sunlight sparkles on the turquoise pool water, emotional wholesome family moment, cheerful father laughter and peaceful water splashes."
    }
]

with open(batch_file, "w", encoding="utf-8") as f:
    for c in cases:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")

print("Prepared batch prompt file with 3 shots:", batch_file, flush=True)

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
print("Starting Sol-H3-Spark batch generation...", flush=True)
subprocess.run(cmd, check=True, env=env)

print("Extracting contact sheets for all shots...", flush=True)
results = json.loads((out / "results.json").read_text())
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
    print("Validated and generated contact sheet for", cid, flush=True)

print("BATCH_COMPLETED_SUCCESSFULLY", out, flush=True)
