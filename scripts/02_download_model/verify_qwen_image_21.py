#!/usr/bin/env python3
"""Verify downloaded files against a captured official ModelScope SHA-256 manifest."""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--manifest", type=Path, required=True)
parser.add_argument("--model", type=Path, required=True)
parser.add_argument("--receipt", type=Path, required=True)
args = parser.parse_args()
manifest = json.loads(args.manifest.read_text())
verified = []
for entry in manifest["Data"]["Files"]:
    if entry["Type"] != "blob":
        continue
    path = args.model / entry["Path"]
    if not path.resolve().is_relative_to(args.model.resolve()):
        raise ValueError("Unexpected path outside model directory")
    if not path.is_file() or path.stat().st_size != entry["Size"]:
        raise ValueError(f"Missing or wrong size: {entry['Path']}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != entry["Sha256"]:
        raise ValueError(f"SHA-256 mismatch: {entry['Path']}")
    verified.append({"path": entry["Path"], "bytes": entry["Size"], "sha256": digest.hexdigest()})
    print("Verified", entry["Path"], flush=True)
args.receipt.write_text(json.dumps({"model": "Qwen/Qwen-Image-2.1", "verified": verified}, indent=2) + "\n")
print(f"PASS: {len(verified)} files", flush=True)
