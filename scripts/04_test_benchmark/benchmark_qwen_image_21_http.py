#!/usr/bin/env python3
"""Measure the SGLang image HTTP service with the resident benchmark's input cases."""
import argparse
import base64
from contextlib import ExitStack
import hashlib
import io
import json
from pathlib import Path
import statistics
import time

import requests
from PIL import Image, ImageStat


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:30010")
    parser.add_argument("--cases-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    args.output.mkdir(parents=True, exist_ok=False)
    cases = []
    for name in ("studio", "teapot-red", "teapot-blue"):
        case = json.loads((args.cases_dir / f"{name}.json").read_text())
        case["name"] = name
        cases.append(case)
    rows = []
    work = [(-1, cases[0])] + [(i, case) for i in range(args.repeats) for case in cases]
    session = requests.Session()
    for iteration, case in work:
        payload = dict(prompt=case["prompt"], size="x".join(map(str, case["size"])),
                       n=1, num_inference_steps=40, guidance_scale=1.0, seed=case["seed"],
                       generator_device="cuda", output_format="png", response_format="b64_json")
        if case["transparency_requested"]:
            payload["background"] = "transparent"
        with ExitStack() as stack:
            start = time.perf_counter()
            if case["references"]:
                files = [("image[]", (Path(p).name, stack.enter_context(open(p, "rb")), "image/png")) for p in case["references"]]
                response = session.post(args.url + "/v1/images/edits", data=payload, files=files, timeout=600)
            else:
                response = session.post(args.url + "/v1/images/generations", json=payload, timeout=600)
            seconds = time.perf_counter() - start
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:2000]}")
        body = response.json()
        data = base64.b64decode(body["data"][0]["b64_json"], validate=True)
        filename = f"sglang-{case['name']}-{'warmup' if iteration == -1 else iteration}.png"
        (args.output / filename).write_bytes(data)
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            histogram = image.getchannel("A").histogram() if "A" in image.getbands() else None
            fraction = sum(histogram[:6]) / (image.width*image.height) if histogram else 0
            check = list(image.size) == case["size"] and max(ImageStat.Stat(image.convert("RGB")).stddev) >= 1
            if case["transparency_requested"]:
                check = check and fraction > .001 and sum(histogram[1:]) > 0
            row = dict(variant="sglang-base", case=case["name"], iteration=iteration, warmup=iteration == -1,
                       http_seconds=seconds, seed=case["seed"], steps=40, size=image.size,
                       transparent_fraction=fraction, alpha_extrema=image.getchannel("A").getextrema() if histogram else None,
                       structural_check_passed=check, sha256=hashlib.sha256(data).hexdigest(), file=filename)
        rows.append(row)
        with (args.output / "requests.jsonl").open("a") as stream:
            stream.write(json.dumps(row) + "\n")
        print(json.dumps(row), flush=True)
    summary = []
    for case in cases:
        selected = [r for r in rows if r["case"] == case["name"] and not r["warmup"]]
        values = [r["http_seconds"] for r in selected]
        summary.append(dict(case=case["name"], median_http_seconds=statistics.median(values),
                            min_seconds=min(values), max_seconds=max(values), requests=len(values),
                            structural_checks_passed=all(r["structural_check_passed"] for r in selected)))
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)
    if not all(r["structural_check_passed"] for r in rows):
        raise SystemExit("Image/alpha validation failed; inspect outputs")


if __name__ == "__main__":
    main()
