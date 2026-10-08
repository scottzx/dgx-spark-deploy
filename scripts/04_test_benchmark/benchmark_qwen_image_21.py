#!/usr/bin/env python3
"""Compare Turbo and base in one resident process, preserving per-request evidence."""
import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import statistics
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=Path("/home/admin/qwen-image-2.1-runtime"))
    parser.add_argument("--model", default="/home/admin/models_cache/Qwen-Image-2.1")
    parser.add_argument("--cases-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--variants", nargs="+", choices=["turbo", "base"], default=["turbo", "base"])
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    args.output.mkdir(parents=True, exist_ok=False)
    locks = []
    for path in (args.runtime / "inference.lock", Path("/home/admin/sol-spark-runtime/inference.lock")):
        handle = path.open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locks.append(handle)
    active = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"], text=True).strip()
    if active:
        raise SystemExit(f"CUDA processes already active: {active}")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import psutil
    if psutil.virtual_memory().available < 48 * 2**30:
        raise SystemExit("Less than 48 GiB available")
    import torch
    from PIL import Image, ImageStat
    from diffusers import QwenImage21Pipeline, FlowMatchEulerDiscreteScheduler

    cases = []
    for name in ("studio", "teapot-red", "teapot-blue"):
        case = json.loads((args.cases_dir / f"{name}.json").read_text())
        case["name"] = name
        case["images"] = []
        for path in case["references"]:
            with Image.open(path) as source:
                case["images"].append(source.copy())
        cases.append(case)
    start = time.perf_counter()
    print("Loading base weights", flush=True)
    pipe = QwenImage21Pipeline.from_pretrained(args.model, dtype=torch.bfloat16, local_files_only=True)
    cpu_loaded = time.perf_counter()
    base_scheduler = dict(pipe.scheduler.config)
    if "turbo" in args.variants:
        print("Loading unmerged Turbo adapter", flush=True)
        pipe.load_lora_weights(str(args.runtime / "turbo"), weight_name="Qwen-Image-2.1-viggle-turbo-v0.2.1-6step-lora-r256.safetensors", local_files_only=True)
    adapter_loaded = time.perf_counter()
    print("Moving pipeline to CUDA", flush=True)
    pipe.to("cuda")
    torch.cuda.synchronize()
    ready = time.perf_counter()
    receipt = {"cpu_load_seconds": cpu_loaded-start, "adapter_load_seconds": adapter_loaded-cpu_loaded,
               "cuda_load_seconds": ready-adapter_loaded, "load_seconds": ready-start,
               "versions": {p: importlib.metadata.version(p) for p in ("torch", "diffusers", "transformers", "peft")},
               "gpu": torch.cuda.get_device_name(), "variants": args.variants,
               "reference_policy": "Identical original base-model red teapot for every edit"}
    (args.output / "environment.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt), flush=True)
    records = []
    for variant in args.variants:
        if variant == "turbo":
            pipe.enable_lora()
            pipe.scheduler = FlowMatchEulerDiscreteScheduler.from_config(base_scheduler, shift_terminal=None)
        else:
            if "turbo" in args.variants:
                pipe.disable_lora()
            pipe.scheduler = FlowMatchEulerDiscreteScheduler.from_config(base_scheduler)
        work = [(-1, cases[0])] + [(i, case) for i in range(args.repeats) for case in cases]
        for iteration, case in work:
            label = f"{variant}-{case['name']}-{'warmup' if iteration == -1 else iteration}"
            torch.cuda.reset_peak_memory_stats()
            options = dict(prompt=case["prompt"], width=case["size"][0], height=case["size"][1],
                           num_inference_steps=6 if variant == "turbo" else 40, true_cfg_scale=1.0,
                           generator=torch.Generator("cuda").manual_seed(case["seed"]))
            if case["images"]:
                options["image"] = case["images"]
            if variant == "turbo":
                options["sigmas"] = [1.0, 0.9375, 0.875, 0.75, 0.5, 0.25]
            torch.cuda.synchronize()
            t0 = time.perf_counter()
            result = pipe(**options).images[0]
            torch.cuda.synchronize()
            t1 = time.perf_counter()
            path = args.output / f"{label}.png"
            result.save(path)
            t2 = time.perf_counter()
            with Image.open(path) as check:
                check.verify()
            histogram = result.getchannel("A").histogram() if "A" in result.getbands() else None
            transparent_fraction = sum(histogram[:6]) / (result.width * result.height) if histogram else 0
            nonuniform = max(ImageStat.Stat(result.convert("RGB")).stddev) >= 1
            alpha_ok = not case["transparency_requested"] or (transparent_fraction > .001 and sum(histogram[1:]) > 0)
            row = dict(variant=variant, case=case["name"], iteration=iteration, warmup=iteration == -1,
                       seed=case["seed"], steps=options["num_inference_steps"], size=result.size,
                       generation_seconds=t1-t0, request_with_save_seconds=t2-t0,
                       peak_cuda_gib=torch.cuda.max_memory_allocated()/2**30,
                       transparent_fraction=transparent_fraction, alpha_extrema=result.getchannel("A").getextrema() if histogram else None,
                       structural_check_passed=nonuniform and alpha_ok,
                       sha256=hashlib.sha256(path.read_bytes()).hexdigest(), file=path.name)
            records.append(row)
            with (args.output / "requests.jsonl").open("a") as stream:
                stream.write(json.dumps(row) + "\n")
            print(json.dumps(row), flush=True)
    summary = []
    for variant in args.variants:
        for case in cases:
            selected = [r for r in records if r["variant"] == variant and r["case"] == case["name"] and not r["warmup"]]
            values = [r["generation_seconds"] for r in selected]
            summary.append(dict(variant=variant, case=case["name"], median_seconds=statistics.median(values),
                                min_seconds=min(values), max_seconds=max(values), requests=len(values),
                                structural_checks_passed=all(r["structural_check_passed"] for r in selected)))
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)
    if not all(r["structural_check_passed"] for r in records):
        raise SystemExit("One or more image/alpha checks failed; inspect requests.jsonl")


if __name__ == "__main__":
    main()
