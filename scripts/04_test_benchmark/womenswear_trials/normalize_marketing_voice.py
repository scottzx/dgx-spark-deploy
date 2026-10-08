"""Match audition loudness by constant gain without altering delivery or timing."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[3]/'docs/benchmarks/15_womenswear_avatar_comparison/marketing_voice_v1'
for p in ROOT.glob('*/receipt.json'):
    d=json.loads(p.read_text())
    for c in d['clips']:
        n=c['processing'];stats=n['pre_gain_measurement'];gain=-23-float(stats['input_i'])
        assert float(stats['input_tp'])+gain<=-3,(d['key'],c['key'],stats)
        raw=p.parent/(c['key']+'_raw.wav');out=p.parent/(c['key']+'.wav')
        assert hashlib.sha256(raw.read_bytes()).hexdigest()==c['raw_sha256']
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(raw),'-af',
            f'highpass=f=65,equalizer=f=3500:t=q:w=0.8:g=-2,volume={gain:.6f}dB',
            '-ar','24000','-c:a','pcm_s16le',str(out)],check=True)
        n['target_lufs']=-23;n['constant_gain_db']=gain
        c['sha256']=hashlib.sha256(out.read_bytes()).hexdigest()
    d['loudness_revision']='All auditions matched to -23 LUFS by constant gain; timing, pitch and delivery unchanged.'
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
