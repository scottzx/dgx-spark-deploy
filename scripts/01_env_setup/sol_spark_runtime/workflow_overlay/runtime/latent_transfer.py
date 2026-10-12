"""Same-request normalized H3 latent and original PCM file handoff."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .config import TASKS
from .duration_profiles import (
    DEFAULT_DURATION_S,
    audio_shape,
    get_profile,
    h3_shape,
    profile_from_h3_T,
    wire_metadata,
)

# Backward-compatible module defaults remain the 5s production profile.
_DEFAULT = get_profile(DEFAULT_DURATION_S)
H3_SHAPE = h3_shape(_DEFAULT)
AUDIO_SHAPE = audio_shape(_DEFAULT)
# 10s handoff is ~5.8MB; keep headroom for future whitelist profiles.
MAX_PAYLOAD_BYTES = 16 * 1024**2
WIRE_METADATA = wire_metadata(_DEFAULT)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024**2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def validate_request_id(request_id):
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", request_id):
        raise ValueError("invalid request_id")
    return request_id


def load_latent_capture(directory, *, request_id=None):
    root = Path(directory).resolve(strict=True)
    path = root / "capture.json"
    row = json.loads(path.read_text())
    if (row.get("status") != "PASS" or row.get("same_request") is not True
            or row.get("external_anchor_used") is not False or row.get("task") not in TASKS
            or row.get("latent_only_transfer") is not True
            or type(row.get("h3_decoder_calls")) is not int or row["h3_decoder_calls"] != 0
            or not isinstance(row.get("prompt"), str) or not row["prompt"].strip()
            or type(row.get("seed")) is not int or type(row.get("source_index")) is not int
            or row["source_index"] < 0):
        raise ValueError("invalid same-request latent-only H3 capture identity")
    validate_request_id(row.get("case_id"))
    if request_id is not None and row.get("request_id") != validate_request_id(request_id):
        raise ValueError("capture belongs to another request")
    payload = (root / "stage1_direct_tensors.pt").resolve(strict=True)
    payload.relative_to(root)
    if (not payload.is_file() or not 0 < payload.stat().st_size <= MAX_PAYLOAD_BYTES
            or sha256(payload) != row.get("payload_sha256")):
        raise ValueError("capture payload size or SHA mismatch")
    return {**row, "payload_path": str(payload), "capture_path": str(path),
            "capture_sha256": sha256(path)}


def load_payload(row, *, torch_module):
    torch = torch_module
    payload = torch.load(row["payload_path"], map_location="cpu", weights_only=True)
    if not isinstance(payload, dict) or set(payload) != {"h3_normalized", "audio"}:
        raise ValueError("unexpected Stage1 tensor keys")
    h3 = payload["h3_normalized"]
    if not isinstance(h3, torch.Tensor) or h3.ndim != 5:
        raise ValueError("invalid H3 h3_normalized tensor")
    profile = profile_from_h3_T(int(h3.shape[2]))
    expected_h3 = h3_shape(profile)
    expected_audio = audio_shape(profile)
    # Prefer capture-declared duration when present; must agree with latent T.
    if row.get("duration_s") is not None and int(row["duration_s"]) != int(profile["duration_s"]):
        raise ValueError(
            f"capture duration_s={row.get('duration_s')} disagrees with H3 T={h3.shape[2]} "
            f"(profile {profile['duration_s']}s)"
        )
    for key, shape, dtype in (("h3_normalized", expected_h3, torch.bfloat16),
                              ("audio", expected_audio, torch.float32)):
        value = payload[key]
        if (not isinstance(value, torch.Tensor) or tuple(value.shape) != shape
                or value.dtype != dtype or not bool(torch.isfinite(value).all())):
            raise ValueError(f"invalid H3 {key} shape/dtype/finite contract: "
                             f"got shape={getattr(value, 'shape', None)} dtype={getattr(value, 'dtype', None)} "
                             f"expected {shape}/{dtype}")
        payload[key] = value.contiguous()
    payload["_duration_profile"] = profile
    return payload
