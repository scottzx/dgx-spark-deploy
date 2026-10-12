"""Sol-H3-Spark duration profiles: 5s (default) and 10s only.

Maps wall-clock duration to Stage1 generation frames and Stage2 emit frames.
Official Spark LTX whitelist is {(124,121), (243,241)}; do not add 15/20/30 here.
"""
from __future__ import annotations

from typing import Any

ALLOWED_DURATION_S = frozenset({5, 10})
DEFAULT_DURATION_S = 5

# Single source of truth for the two unlocked Spark profiles.
PROFILES: dict[int, dict[str, Any]] = {
    5: {
        "duration_s": 5,
        "stage1_frames": 124,
        "emit_frames": 121,
        "h3_T": 37,
        "ltx_T_full": 17,
        "ltx_T_used": 16,
        "padded_canvas_frames": 129,
        "audio_samples": 161333,
        "fps": 24.0,
        "audio_sample_rate": 32000,
        "pixel_height_stage1": 384,
        "pixel_width_stage1": 672,
        "pixel_height_stage2": 768,
        "pixel_width_stage2": 1344,
    },
    10: {
        "duration_s": 10,
        "stage1_frames": 243,
        "emit_frames": 241,
        "h3_T": 72,
        "ltx_T_full": 32,
        "ltx_T_used": 31,
        "padded_canvas_frames": 249,
        "audio_samples": 321333,
        "fps": 24.0,
        "audio_sample_rate": 32000,
        "pixel_height_stage1": 384,
        "pixel_width_stage1": 672,
        "pixel_height_stage2": 768,
        "pixel_width_stage2": 1344,
    },
}

_H3_T_TO_DURATION = {p["h3_T"]: d for d, p in PROFILES.items()}
_EMIT_TO_DURATION = {p["emit_frames"]: d for d, p in PROFILES.items()}


def validate_duration_s(value: Any) -> int:
    try:
        duration = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"duration_s must be int in {sorted(ALLOWED_DURATION_S)}, got {value!r}") from exc
    if duration not in ALLOWED_DURATION_S:
        raise ValueError(f"duration_s must be one of {sorted(ALLOWED_DURATION_S)}, got {duration}")
    return duration


def get_profile(duration_s: Any = DEFAULT_DURATION_S) -> dict[str, Any]:
    duration = validate_duration_s(duration_s if duration_s is not None else DEFAULT_DURATION_S)
    return dict(PROFILES[duration])


def profile_from_h3_T(h3_T: int) -> dict[str, Any]:
    if h3_T not in _H3_T_TO_DURATION:
        raise ValueError(f"unsupported H3 latent T={h3_T}; expected one of {sorted(_H3_T_TO_DURATION)}")
    return get_profile(_H3_T_TO_DURATION[h3_T])


def profile_from_emit(emit_frames: int) -> dict[str, Any]:
    if emit_frames not in _EMIT_TO_DURATION:
        raise ValueError(f"unsupported emit frames={emit_frames}; expected one of {sorted(_EMIT_TO_DURATION)}")
    return get_profile(_EMIT_TO_DURATION[emit_frames])


def h3_shape(profile: dict[str, Any]) -> tuple[int, int, int, int, int]:
    return (1, 24, int(profile["h3_T"]), 24, 42)


def h3_upscaled_shape(profile: dict[str, Any]) -> tuple[int, int, int, int, int]:
    return (1, 24, int(profile["h3_T"]), 48, 84)


def adapter_output_shape(profile: dict[str, Any]) -> tuple[int, int, int, int, int]:
    return (1, 128, int(profile["ltx_T_full"]), 24, 42)


def refiner_input_shape(profile: dict[str, Any]) -> tuple[int, int, int, int, int]:
    return (1, 128, int(profile["ltx_T_used"]), 24, 42)


def audio_shape(profile: dict[str, Any]) -> tuple[int, int, int]:
    return (1, 2, int(profile["audio_samples"]))


def wire_metadata(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "input_variant": "h3_adapter",
        "primary_kind": "h3_normalized_latent",
        "normalization": "released_h3_per_channel_mean_std",
        "generation_frames": int(profile["stage1_frames"]),
        "adapter_pixel_frames": int(profile["stage1_frames"]),
        "padded_canvas_frames": int(profile["padded_canvas_frames"]),
        "emitted_frames": int(profile["emit_frames"]),
        "pixel_height": int(profile["pixel_height_stage1"]),
        "pixel_width": int(profile["pixel_width_stage1"]),
        "fps": float(profile["fps"]),
        "audio_sample_rate": int(profile["audio_sample_rate"]),
        "duration_s": int(profile["duration_s"]),
    }


def apply_env(profile: dict[str, Any]) -> None:
    """Set H3_LTX_* for this process (Stage2 worker / tests). Default remains 5s when unset."""
    import os

    os.environ["H3_LTX_SOURCE_FRAMES"] = str(profile["stage1_frames"])
    os.environ["H3_LTX_OUTPUT_FRAMES"] = str(profile["emit_frames"])
