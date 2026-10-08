"""Independent shots and AV continuation share one resident FL2VA pipeline."""
import json
from pathlib import Path
import re
import subprocess
import time

from .duration_profiles import get_profile
from .stage1_ops.continuation import window_geometry

FFMPEG = '/home/admin/.local/bin/ffmpeg'


def concatenate_clips(clips, frame_counts, output):
    """Discard AAC padding and regenerate PTS from frames, not MP4 duration."""
    if not clips or len(clips) != len(frame_counts):
        raise ValueError('Provide one frame count per clip')
    command = [FFMPEG, '-y']
    filters, streams = [], []
    for i, (clip, count) in enumerate(zip(clips, frame_counts)):
        command.extend(['-i', str(clip)])
        filters.append(f'[{i}:v]trim=end_frame={count},setpts=N/(24*TB)[v{i}]')
        samples = round(count/24*32000)
        filters.append(f'[{i}:a]atrim=end_sample={samples},asetpts=PTS-STARTPTS[a{i}]')
        streams.extend([f'[v{i}]', f'[a{i}]'])
    filters.append(''.join(streams)+f'concat=n={len(clips)}:v=1:a=1[cv][a]')
    filters.append('[cv]setpts=N/(24*TB)[v]')
    command.extend(['-filter_complex', ';'.join(filters), '-map', '[v]', '-map', '[a]',
        '-vsync', '0', '-c:v', 'libx264', '-preset', 'fast', '-crf', '19',
        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '32000', '-ac', '2', '-b:a', '192k', str(output)])
    subprocess.run(command, check=True, capture_output=True)


def validate_workflow(case):
    transition = case.get('transition', 'independent')
    if transition not in ('independent', 'continue'):
        raise ValueError('transition must be independent or continue')
    previous = case.get('previous_clip_id')
    if transition == 'continue':
        if case.get('task', 'fl2va') not in ('fl2va', 'ref2va'):
            raise ValueError('Continuation requires the fl2va or ref2va partition')
        if not isinstance(previous, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', previous):
            raise ValueError('continue requires a file-safe previous_clip_id')
        if case.get('first_frame') or case.get('capture_dir'):
            raise ValueError('continue derives its first_frame from previous_clip_id; do not supply first_frame/capture_dir')
        if case.get('context_frames', 22) not in (5, 22, 39, 56):
            raise ValueError('context_frames must be 5, 22, 39 or 56')
        audio = case.get('audio_context_frames', 24)
        if type(audio) is not int or not 3 <= audio <= 120 or audio % 3:
            raise ValueError('audio_context_frames must be a multiple of 3 between 3 and 120')
    elif previous is not None:
        raise ValueError('independent must not carry previous_clip_id')
    return transition


def prepare_case(pipeline, case):
    # Called before any worker command, so invalid predecessors cannot poison
    # persistent model sessions or leave a RUNNING request directory behind.
    transition = validate_workflow(case)
    case = dict(case, transition=transition)
    if transition == 'independent':
        case.pop('previous_capture_dir', None)
        return case
    matches = [r for r in pipeline.report['requests']
        if r['case_id'] == case['previous_clip_id'] and r['status'] == 'PASS']
    if len(matches) != 1:
        raise ValueError('previous_clip_id must identify a completed clip in this pipeline session')
    previous = matches[0]
    capture = Path(previous['capture_dir']).resolve(strict=True)
    receipt = json.loads((capture / 'capture.json').read_text())
    if not receipt.get('continuation_state_sha256'):
        raise ValueError('Previous clip has no saved AV continuation state')
    profile = get_profile(receipt['duration_s'])
    _, _, trim, _ = window_geometry(profile['h3_T'], case.get('context_frames', 22),
        profile['stage1_frames'], profile['emit_frames'])
    # A frame presented to Qwen identifies the actor/set. Actual H3 motion and
    # audio conditions come from the verified latent prefix, not this image.
    if case.get('task', 'fl2va') == 'fl2va':
        anchor = pipeline.root / f"{case['case_id']}_continuation_anchor.png"
        subprocess.run([FFMPEG, '-y', '-i', previous['output'], '-vf',
            f"select=eq(n\\,{previous['delivered_frames']-1})", '-frames:v', '1', str(anchor)],
            check=True, capture_output=True)
        if not anchor.is_file():
            raise ValueError('Could not extract the predecessor delivery endpoint')
        case['first_frame'] = str(anchor)
    # Ref2VA keeps its ordered subject assets; its Qwen receipt must not gain
    # a first-frame input or silently renumber the reference labels.
    case.update(previous_capture_dir=str(capture), trim_frames=trim,
        context_frames=case.get('context_frames', 22), audio_context_frames=case.get('audio_context_frames', 24))
    return case


def finish_clip(pipeline, case, row):
    receipt = json.loads((Path(row['capture_dir']) / 'capture.json').read_text())
    profile = get_profile(receipt['duration_s'])
    trim = int(receipt.get('continuation', {}).get('trim_frames', 0))
    # The draft decoder emits a full H3 canvas. Conform its tail to the same
    # delivered timeline as Stage2 before a clip is allowed to be continued.
    emit = profile['emit_frames']
    raw = Path(row['output'])
    if trim or row['mode'] == 'draft':
        delivered = raw.with_name(raw.stem + '_delivered.mp4')
        vf = f'trim=start_frame={trim}:end_frame={emit},setpts=PTS-STARTPTS'
        af = (f'atrim=start_sample={round(trim/24*32000)}:'
              f'end_sample={round(emit/24*32000)},asetpts=PTS-STARTPTS')
        subprocess.run([FFMPEG, '-y', '-i', str(raw), '-vf', vf, '-af', af,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '19', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-ar', '32000', '-ac', '2', '-b:a', '192k', str(delivered)],
            check=True, capture_output=True)
        row.update(untrimmed_output=str(raw), output=str(delivered))
    row.update(transition=case.get('transition', 'independent'), previous_clip_id=case.get('previous_clip_id'),
        context_frames=case.get('context_frames', 0), trim_frames=trim,
        delivered_frames=emit-trim, delivered_duration_s=(emit-trim)/24,
        continuation=receipt.get('continuation'), continuation_state_available=True)
    ended = time.monotonic_ns()
    row.update(final_mp4_complete_monotonic_ns=ended,
        e2e_s=(ended-row['request_start_monotonic_ns'])/1e9)
    (Path(row['output']).parent / 'workflow_result.json').write_text(json.dumps(row, indent=2)+'\n')
    return row
