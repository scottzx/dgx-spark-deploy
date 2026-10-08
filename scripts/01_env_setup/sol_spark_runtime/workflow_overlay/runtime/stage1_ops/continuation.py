"""Per-request motion/audio continuation for the pinned FastVideo H3 worker.

The external checkout is untouched. Conditions are frozen prefix rows on the
target timeline; they are not references on a separate timeline. Implementation
uses the installed FastVideo packing helpers and its native scheduler loop.
"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

FRAME_SPANS = (1, 4, 4, 4, 4)
CONTEXT_WINDOWS = {5: 2, 22: 7, 39: 12, 56: 17}
FRAME_SCALE = 5 / 3


def window_geometry(total_steps, context_frames, generation_frames, emit_frames):
    if context_frames not in CONTEXT_WINDOWS:
        raise ValueError('context_frames must be 5, 22, 39 or 56')
    steps = CONTEXT_WINDOWS[context_frames]
    start = total_steps - steps
    if start < 0 or start % 5:
        raise ValueError('H3 context does not start on its five-step temporal cycle')
    if sum(FRAME_SPANS[k % 5] for k in range(total_steps)) != generation_frames:
        raise ValueError('Context tensor and generation frame count disagree')
    # Spark refines 124->121 / 243->241. Preserve the unseen raw suffix in the
    # NEXT delivery, rather than skipping it by trimming the full context run.
    trim = context_frames - (generation_frames - emit_frames)
    if trim <= 0:
        raise ValueError('Context window ends before the delivered clip')
    offsets, cursor = [], 0
    for k in range(steps):
        offsets.append(cursor)
        cursor += FRAME_SPANS[k % 5]
    return start, steps, trim, offsets


def load_context(directory, context_frames, audio_context_frames):
    import torch
    root = Path(directory).resolve(strict=True)
    receipt = json.loads((root / 'capture.json').read_text())
    path = root / 'continuation_state.pt'
    if (receipt.get('status') != 'PASS' or not path.is_file()
            or path.stat().st_size > 32 * 1024**2
            or hashlib.sha256(path.read_bytes()).hexdigest() != receipt.get('continuation_state_sha256')):
        raise ValueError('Previous clip has no verified continuation state; regenerate it with this overlay')
    payload = torch.load(path, map_location='cpu', weights_only=True)
    video, audio = payload['video'], payload['audio']
    if (video.ndim != 5 or tuple(video.shape[:2]) != (1, 24)
            or tuple(video.shape[3:]) != (24, 42) or audio.ndim != 3 or audio.shape[0] != 2
            or not torch.isfinite(video).all() or not torch.isfinite(audio).all()):
        raise ValueError('Invalid continuation AV geometry or values')
    start, steps, trim, offsets = window_geometry(int(video.shape[2]), context_frames,
        int(receipt['stage1_frames']), int(receipt['emit_frames']))
    # Previous delivery ends before H3's raw tail. Snap that endpoint to the
    # native 40 Hz grid; never take the raw file's audio end as the join.
    audio_end = round(int(receipt['emit_frames']) * FRAME_SCALE)
    audio_steps = round(audio_context_frames * FRAME_SCALE)
    if not 0 < audio_steps <= audio_end <= audio.shape[-1]:
        raise ValueError('Audio context exceeds the previous delivery')
    return dict(video=video[:, :, start:start+steps].float(),
        audio=audio[:, :, audio_end-audio_steps:audio_end].float(),
        trim_frames=trim, offsets=offsets, audio_steps=audio_steps,
        source_capture=str(root), source_sha256=receipt['continuation_state_sha256'],
        source_emit_frames=int(receipt['emit_frames']))


def build_layout(old, video_steps, audio_steps, offsets, trim_frames, keep_last, keep_references=False):
    import torch
    from fastvideo.pipelines.basic.minimax_h3.packing import _fill_audio_positions
    ntext = old.text_indices.numel()
    target_video = old.video_indices[old.num_condition_video_rows:]
    target_audio = old.audio_indices[old.num_condition_audio_rows:]
    rows_per_step = target_video.numel() // old.num_video_latent_frames
    clean_rows = video_steps * rows_per_step
    native_video_rows = old.num_condition_video_rows if keep_references else (rows_per_step if keep_last else 0)
    native_audio_rows = old.num_condition_audio_rows if keep_references else 0
    nvideo = clean_rows + native_video_rows
    naudio = 2 * audio_steps + native_audio_rows
    audio_start = ntext + nvideo
    video_start = audio_start + naudio + target_audio.numel()
    length = video_start + target_video.numel()
    positions = torch.zeros((length, 3), dtype=torch.float64)
    positions[:ntext] = old.position_ids[old.text_indices]
    spatial = old.position_ids[target_video[:rows_per_step], 1:]
    origin = float(old.position_ids[target_video[0], 0])
    for k, offset in enumerate(offsets):
        span = slice(ntext+k*rows_per_step, ntext+(k+1)*rows_per_step)
        positions[span, 0] = origin + offset * FRAME_SCALE
        positions[span, 1:] = spatial
    if keep_references:
        positions[ntext+clean_rows:audio_start] = old.position_ids[
            old.video_indices[:old.num_condition_video_rows]]
    elif keep_last:
        positions[ntext+clean_rows:audio_start] = old.position_ids[
            old.video_indices[old.num_condition_video_rows-rows_per_step:old.num_condition_video_rows]]
    # Native stereo audio rows are channel-major. The audio window ENDS at
    # the delivered-video join, rather than at the raw H3 generation endpoint.
    width_grid = torch.unique(spatial[:, 1], sorted=True)
    _fill_audio_positions(positions, slice(audio_start, audio_start+2*audio_steps), audio_steps,
        origin + round(trim_frames*FRAME_SCALE) - audio_steps, width_grid)
    if native_audio_rows:
        positions[audio_start+2*audio_steps:audio_start+naudio] = old.position_ids[
            old.audio_indices[:native_audio_rows]]
    positions[audio_start+naudio:video_start] = old.position_ids[target_audio]
    positions[video_start:] = old.position_ids[target_video]
    video_indices = torch.cat((torch.arange(ntext, audio_start), torch.arange(video_start, length)))
    audio_indices = torch.arange(audio_start, video_start)
    tags = torch.empty(length, dtype=torch.long)
    tags[:ntext] = old.token_tags[old.text_indices]
    tags[video_indices] = 0
    tags[audio_indices] = 2
    return replace(old, sequence_length=length, position_ids=positions, token_tags=tags,
        text_indices=torch.arange(ntext), video_indices=video_indices, audio_indices=audio_indices,
        num_condition_video_rows=nvideo, num_condition_audio_rows=naudio), clean_rows


def install(worker):
    import torch
    from fastvideo.pipelines.basic.minimax_h3 import packing
    from fastvideo.pipelines.basic.minimax_h3.stages import minimax_h3_denoising as denoise_module
    from fastvideo.pipelines.basic.minimax_h3.stages.minimax_h3_latent_preparation import MINIMAX_H3_LAYOUT_KEY
    state = worker._sol_h3_stage1
    stages = worker.pipeline._stage_name_mapping
    preparation = stages['latent_preparation_stage']
    original_prepare = preparation.forward
    original_timesteps = denoise_module.build_row_timesteps
    original_denoise = stages['denoising_stage'].forward
    active = {'layout': None, 'clean_rows': 0}

    def prepare(batch, args):
        active.update(layout=None, clean_rows=0)
        state['continuation_audit'] = None
        batch = original_prepare(batch, args)
        case = state['case']['case']
        if case.get('transition', 'independent') != 'continue':
            return batch
        if state['task'] not in ('fl2va', 'ref2va'):
            raise ValueError('Motion continuation requires fl2va or ref2va')
        context = load_context(case['previous_capture_dir'], case.get('context_frames', 22),
            case.get('audio_context_frames', 24))
        old = batch.extra[MINIMAX_H3_LAYOUT_KEY]
        patch = packing.h3_dit_patch_size(args)
        if patch[0] != 1:
            raise ValueError('Continuation requires one temporal latent per DiT patch')
        clean = packing.patchify_video_latents(context['video'], patch).to(batch.latents.device)
        keep_last = bool(case.get('last_frame'))
        keep_references = state['task'] == 'ref2va'
        target = batch.latents[old.num_condition_video_rows:]
        conditions = [clean]
        if keep_references:
            conditions.append(batch.latents[:old.num_condition_video_rows])
        elif keep_last:
            r = target.shape[0] // old.num_video_latent_frames
            conditions.append(batch.latents[old.num_condition_video_rows-r:old.num_condition_video_rows])
        batch.latents = torch.cat((*conditions, target))
        pinned_audio = context['audio'].permute(0, 2, 1).reshape(-1, context['audio'].shape[1])
        old_audio = batch.audio_latents if keep_references else batch.audio_latents[old.num_condition_audio_rows:]
        batch.audio_latents = torch.cat((pinned_audio.to(batch.audio_latents.device), old_audio))
        layout, count = build_layout(old, context['video'].shape[2], context['audio_steps'],
            context['offsets'], context['trim_frames'], keep_last, keep_references)
        batch.extra[MINIMAX_H3_LAYOUT_KEY] = layout
        active.update(layout=layout, clean_rows=count)
        state['continuation_audit'] = dict(
            source_capture=context['source_capture'], source_sha256=context['source_sha256'],
            context_frames=case.get('context_frames', 22), trim_frames=context['trim_frames'],
            audio_context_frames=case.get('audio_context_frames', 24),
            condition_video_rows=layout.num_condition_video_rows,
            condition_audio_rows=layout.num_condition_audio_rows,
            video_timeline_offsets=context['offsets'], audio_join_frame=context['trim_frames'],
            frozen_prefix_verified=False, method='native_H3_AV_latent_timeline_prefix')
        state['continuation_audit'].update(reference_video_rows_preserved=old.num_condition_video_rows if keep_references else 0,
            reference_audio_rows_preserved=old.num_condition_audio_rows if keep_references else 0,
            reference_count=len(case.get('references', [])))
        return batch

    def timesteps(layout, **values):
        unique, inverse = original_timesteps(layout, **values)
        if layout is active['layout']:
            rows = unique[inverse]
            rows[layout.video_indices[:active['clean_rows']]] = 1.0
            return torch.unique(rows, sorted=True, return_inverse=True)
        return unique, inverse

    def denoise(batch, args):
        layout = batch.extra[MINIMAX_H3_LAYOUT_KEY]
        continuing = layout is active['layout']
        if continuing:
            video = batch.latents[:layout.num_condition_video_rows].clone()
            audio = batch.audio_latents[:layout.num_condition_audio_rows].clone()
        result = original_denoise(batch, args)
        if continuing:
            if (not torch.equal(video, result.latents[:layout.num_condition_video_rows]) or
                    not torch.equal(audio, result.audio_latents[:layout.num_condition_audio_rows])):
                raise RuntimeError('Pinned continuation rows changed during denoising')
            state['continuation_audit']['frozen_prefix_verified'] = True
        return result

    preparation.forward = prepare
    denoise_module.build_row_timesteps = timesteps
    stages['denoising_stage'].forward = denoise
