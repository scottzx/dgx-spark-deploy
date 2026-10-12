#!/usr/bin/env python3
"""Decode Stage1 H3 latents to a ~384x672 draft MP4 via TAEH3 preview decoder."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import torch

FASTVIDEO = Path("/home/admin/sol-spark-runtime/sources/FastVideo")
sys.path.insert(0, str(FASTVIDEO))

from fastvideo.models.vaes.minimax_h3_taeh3 import (  # noqa: E402
    decode_ncthw_latents_taeh3,
    ensure_taeh3_checkpoint,
    taeh3_decoded_pixel_shape,
)

FFMPEG = "/home/admin/.local/bin/ffmpeg"


def _write_wav(path: Path, audio: torch.Tensor, sample_rate: int = 32000) -> None:
    x = audio.detach().float().cpu()
    if x.ndim == 3:
        x = x[0]
    if x.ndim != 2:
        raise ValueError(f"unexpected audio shape {tuple(audio.shape)}")
    if x.shape[0] != 2 and x.shape[1] == 2:
        x = x.T
    pcm = (x.clamp(-1, 1).numpy() * 32767.0).astype(np.int16)
    interleaved = pcm.T.reshape(-1)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(interleaved.tobytes())


def _write_raw_rgb(path: Path, pixels_ncthw: torch.Tensor) -> tuple[int, int, int]:
    x = pixels_ncthw[0].detach().float().cpu().clamp(0, 1)
    c, t, h, w = map(int, x.shape)
    if c != 3:
        raise ValueError(f"expected RGB, got {c}")
    arr = (x.permute(1, 2, 3, 0).contiguous().numpy() * 255.0).astype(np.uint8)
    path.write_bytes(arr.tobytes())
    return t, h, w


def render_draft(capture_dir: Path, output_mp4: Path, *, device: str = "cpu") -> dict:
    capture_dir = capture_dir.resolve()
    capture = json.loads((capture_dir / "capture.json").read_text())
    payload = torch.load(capture_dir / "stage1_direct_tensors.pt", map_location="cpu", weights_only=True)
    latents = payload["h3_normalized"]
    audio = payload["audio"]
    expected = taeh3_decoded_pixel_shape(tuple(latents.shape))
    ensure_taeh3_checkpoint()
    use_cuda = device.startswith("cuda") and torch.cuda.is_available()
    dev = torch.device(device if use_cuda or device == "cpu" else "cpu")
    pixels = decode_ncthw_latents_taeh3(latents, device=dev)
    if tuple(pixels.shape) != expected:
        raise RuntimeError(f"TAEH3 shape {tuple(pixels.shape)} != {expected}")

    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    raw = output_mp4.with_suffix(".rgb")
    wav = output_mp4.with_suffix(".wav")
    t, h, w = _write_raw_rgb(raw, pixels)
    _write_wav(wav, audio, sample_rate=32000)
    tmp = output_mp4.with_suffix(".tmp.mp4")
    subprocess.run(
        [
            FFMPEG,
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{w}x{h}",
            "-r",
            "24",
            "-i",
            str(raw),
            "-i",
            str(wav),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "23",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            str(tmp),
        ],
        check=True,
        capture_output=True,
    )
    tmp.replace(output_mp4)
    raw.unlink(missing_ok=True)
    wav.unlink(missing_ok=True)
    return {
        "status": "PASS",
        "output": str(output_mp4),
        "frames": t,
        "height": h,
        "width": w,
        "case_id": capture.get("case_id"),
        "decoder": "taeh3_preview",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--capture-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--device", default="cpu")
    args = p.parse_args()
    print(json.dumps(render_draft(args.capture_dir, args.output, device=args.device), ensure_ascii=False))


if __name__ == "__main__":
    main()
