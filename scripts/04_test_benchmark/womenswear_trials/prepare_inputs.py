"""Bind actual LTX motion, identical narration and shared first frame to all routes."""
import hashlib
import json
import shutil
import subprocess
from config import ROOT, CASES, prompt

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

jobs = []
for index, (key, label, appearance, text) in enumerate(CASES):
    case = ROOT/'inputs'/key
    case.mkdir(parents=True, exist_ok=True)
    files = {
        'driver.mp4': ROOT/'ltx'/key/'motion.mp4',
        'audio.wav': ROOT/'voices'/f'{key}.wav',
        'audio_16k.wav': ROOT/'voices'/f'{key}_16k.wav',
        'reference.png': ROOT/'assets/empty.png',
    }
    for name, source in files.items():
        shutil.copy2(source, case/name)
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(case/'driver.mp4'),
                    '-frames:v','1',str(case/'first_frame.png')],check=True)
    hashes={name:sha(case/name) for name in [*files,'first_frame.png']}
    (case/'prompt.txt').write_text(prompt(appearance)+'\n')
    jobs.append({'product':key,'label':label,'directory':str(case),'seed':2026100810+index,
                 'duration_seconds':8.04,'frames':201,'fps':25,'text':text,
                 'input_sha256':hashes,'input_kind':'generated_LTX_video',
                 'prompt':prompt(appearance)})
(ROOT/'inputs/manifest.json').write_text(json.dumps(jobs,ensure_ascii=False,indent=2)+'\n')
shutil.copy2(ROOT/'voices/voice.json',ROOT/'inputs/voice.json')
print(json.dumps({'stage':'inputs_ready','cases':len(jobs)},ensure_ascii=False),flush=True)
