"""Use the approved Serena default WAVs unchanged in isolated synthesis inputs."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
import soundfile as sf

BASE = Path('/home/admin/womenswear-avatar-tests')
ROOT = Path(os.environ.get('AVATAR_BENCH_ROOT', '/home/admin/womenswear-avatar-natural-v2'))
SOURCE = BASE/'natural_voice_v2/serena_default'
ROOT.mkdir(parents=True, exist_ok=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
receipt = json.loads((SOURCE/'receipt.json').read_text())
assert receipt['speaker'] == 'Serena' and receipt['instruction'] == ''
clips = {r['key']: r for r in receipt['clips']}
baseline_jobs = json.loads((BASE/'inputs/manifest.json').read_text())
records, jobs, previews = [], [], []
for source_job in baseline_jobs:
    key = source_job['product']
    record = clips[key]
    speech_path = SOURCE/f'{key}.wav'
    assert sha(speech_path) == record['sha256']
    speech, sr = sf.read(speech_path, dtype='float32')
    assert sr == 24000 and speech.ndim == 1 and np.isfinite(speech).all()
    start, total = 2.4, 8.04
    assert start + len(speech)/sr < total - 1.5
    out = ROOT/'voices'
    out.mkdir(exist_ok=True)
    shutil.copy2(speech_path, out/f'{key}_speech.wav')
    audio = np.zeros(round(total*sr), dtype=np.float32)
    offset = round(start*sr)
    audio[offset:offset+len(speech)] = speech
    sf.write(out/f'{key}.wav', audio, sr, subtype='PCM_16')
    decoded, _ = sf.read(out/f'{key}.wav', dtype='float32')
    assert np.array_equal(decoded[offset:offset+len(speech)], speech)
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(out/f'{key}.wav'),
                    '-ar','16000','-c:a','pcm_s16le',str(out/f'{key}_16k.wav')], check=True)
    case = ROOT/'inputs'/key
    case.mkdir(parents=True, exist_ok=True)
    original = Path(source_job['directory'])
    for name in ('driver.mp4','reference.png','first_frame.png','prompt.txt'):
        shutil.copy2(original/name, case/name)
    shutil.copy2(out/f'{key}.wav', case/'audio.wav')
    shutil.copy2(out/f'{key}_16k.wav', case/'audio_16k.wav')
    input_sha = {name:sha(case/name) for name in source_job['input_sha256']}
    assert input_sha['driver.mp4'] == source_job['input_sha256']['driver.mp4']
    job = dict(source_job, directory=str(case), text=record['text'], input_sha256=input_sha,
               voice_profile='serena_default', approved_voice_source_sha256=record['sha256'],
               baseline_input_sha256=source_job['input_sha256'])
    jobs.append(job)
    records.append({'product':key,'text':record['text'],'speaker':'Serena',
                    'speech_duration_seconds':len(speech)/sr,
                    'narration_starts_seconds':start,'narration_ends_seconds':start+len(speech)/sr,
                    'duration_seconds':total,'sample_rate':sr,'sha256':sha(out/f'{key}.wav'),
                    'speech_sha256':record['sha256'],'approved_samples_unchanged':True,
                    'pitch_changed':False,'speed_changed':False,'gain_changed':False})
    previews.extend((speech, np.zeros(round(.18*sr), dtype=np.float32)))
sf.write(ROOT/'voices/voice_preview.wav', np.concatenate(previews), 24000)
voice = {'profile':'serena_default','model':receipt['model'],'speaker':'Serena','instruction':'',
         'approved_source':str(SOURCE),'source_receipt_sha256':sha(SOURCE/'receipt.json'),
         'clips':records,'policy':'Exact approved short WAV samples, only placed at 2.4s in an 8.04s timeline. No time stretch, pitch change, additional EQ or gain.'}
(ROOT/'voices/voice.json').write_text(json.dumps(voice,ensure_ascii=False,indent=2)+'\n')
shutil.copy2(ROOT/'voices/voice.json', ROOT/'inputs/voice.json')
(ROOT/'inputs/manifest.json').write_text(json.dumps(jobs,ensure_ascii=False,indent=2)+'\n')
(ROOT/'synthesis_provenance.json').write_text(json.dumps({
    'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'voice_profile':'serena_default','baseline_root':str(BASE),'root':str(ROOT),
    'policy':'Same images, LTX driver, motion prompts and seeds as baseline; all three speaking models rerun with approved natural audio.',
    'ltx_motion_regenerated':False,'speaking_videos_regenerated':True,
    'approved_audio':records},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'prepared':True,'root':str(ROOT),'products':len(jobs)},ensure_ascii=False),flush=True)
