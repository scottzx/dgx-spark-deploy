#!/usr/bin/env python3
"""Generate local Qwen-Image-2.1 assets, including reference edits and RGBA PNGs."""
import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", type=Path, action="append", default=[])
    parser.add_argument("--transparent", action="store_true")
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", type=Path, default=Path("/home/admin/models_cache/Qwen-Image-2.1"))
    parser.add_argument("--runtime", type=Path, default=Path("/home/admin/qwen-image-2.1-runtime"))
    args = parser.parse_args()
    if args.output.suffix.lower() != ".png":
        parser.error("--output must be a PNG file")
    if args.output.exists() or args.output.with_suffix(".json").exists():
        parser.error("Output or metadata already exists; choose a new filename")
    if min(args.width, args.height) < 256 or args.width % 32 or args.height % 32:
        parser.error("Width and height must be multiples of 32, at least 256")
    if args.steps < 1 or len(args.image) > 10:
        parser.error("Use positive steps and at most 10 reference images")
    for path in args.image:
        if not path.is_file():
            parser.error(f"Reference image missing: {path}")

    args.runtime.mkdir(parents=True, exist_ok=True)
    # Keep descriptors open for the complete generation. Never unlink lock files.
    locks = []
    for path in (args.runtime / "inference.lock", Path("/home/admin/sol-spark-runtime/inference.lock")):
        if path.parent.exists():
            lock = path.open("a")
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SystemExit(f"Another image/video batch is running: {path}")
            locks.append(lock)

    import psutil
    processes = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if processes:
        raise SystemExit(f"Other CUDA compute processes are running (PIDs: {processes}); stop them before asset generation.")
    available = psutil.virtual_memory().available / 2**30
    if available < 48:
        raise SystemExit(f"Only {available:.1f} GiB system memory available; release other model services first (48 GiB required).")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    import torch
    from PIL import Image, ImageStat
    from diffusers import QwenImage21Pipeline

    if not torch.cuda.is_available():
        raise SystemExit("CUDA is unavailable")
    prompt = args.prompt
    if args.transparent:
        prompt = ("This is an RGBA image with transparency. " + prompt +
                  " The image has alpha channel and the background is transparent.")
    images = []
    for path in args.image:
        with Image.open(path) as image:
            images.append(image.copy())
    started = time.monotonic()
    print("Loading Qwen-Image-2.1 BF16 from local weights", flush=True)
    pipe = QwenImage21Pipeline.from_pretrained(
        str(args.model), dtype=torch.bfloat16, local_files_only=True,
    ).to("cuda")
    torch.cuda.synchronize()
    loaded = time.monotonic()
    options = dict(prompt=prompt, width=args.width, height=args.height,
                   num_inference_steps=args.steps,
                   generator=torch.Generator("cuda").manual_seed(args.seed))
    if images:
        options["image"] = images
    result = pipe(**options).images[0]
    torch.cuda.synchronize()
    generated = time.monotonic()
    if max(ImageStat.Stat(result.convert("RGB")).stddev) < 1:
        raise RuntimeError("Generated image is nearly uniform; validation failed")
    alpha = result.getchannel("A") if "A" in result.getbands() else None
    alpha_extrema = alpha.getextrema() if alpha is not None else None
    alpha_histogram = alpha.histogram() if alpha is not None else None
    pixel_count = result.width * result.height
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".partial.png")
    result.save(temporary)
    with Image.open(temporary) as check:
        check.verify()
    temporary.replace(args.output)
    metadata = {
        "model": str(args.model), "prompt": prompt, "seed": args.seed,
        "steps": args.steps, "size": list(result.size), "mode": result.mode,
        "references": [str(p.resolve()) for p in args.image],
        "transparency_requested": args.transparent, "alpha_extrema": alpha_extrema,
        "has_transparent_pixels": alpha_extrema is not None and alpha_extrema[0] < 255,
        "transparent_pixel_fraction": round(sum(alpha_histogram[:6]) / pixel_count, 4) if alpha_histogram else None,
        "opaque_pixel_fraction": round(sum(alpha_histogram[250:]) / pixel_count, 4) if alpha_histogram else None,
        "load_seconds": round(loaded - started, 2),
        "generation_seconds": round(generated - loaded, 2),
        "total_seconds": round(generated - started, 2),
        "peak_cuda_allocated_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2),
        "gpu": torch.cuda.get_device_name(),
        "load_method": "cpu_then_cuda",
        "versions": {p: importlib.metadata.version(p) for p in ("torch", "diffusers", "transformers")},
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }
    args.output.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metadata, ensure_ascii=False, indent=2), flush=True)
    if args.transparent and (not metadata["has_transparent_pixels"] or
                             metadata["transparent_pixel_fraction"] <= 0.001 or alpha_extrema[1] == 0):
        raise SystemExit("Image saved, but transparency validation failed; inspect output and metadata")


if __name__ == "__main__":
    main()
