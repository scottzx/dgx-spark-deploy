"""Preserve native output and normalize only an exact 40 ms rounding tail."""
import json
from pathlib import Path
import shutil
import subprocess
from bench_common import ROOT, jobs, mux, sha

inputs = {j['product']:j for j in jobs()}
for path in (ROOT/'outputs').glob('*/*/metrics.json'):
    data=json.loads(path.read_text())
    if data.get('final_frame_hold_seconds'): continue
    output=path.parent/'video.mp4'
    if not output.exists(): continue
    stream=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
                                               '-show_streams','-of','json',str(output)]))['streams'][0]
    if int(stream.get('nb_frames',0))!=200: continue
    native=Path(data['native_output'])
    raw=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
                                            '-show_streams','-of','json',str(native)]))['streams'][0]
    if int(raw.get('nb_frames',0))!=200 or raw.get('avg_frame_rate')!='25/1' or abs(float(raw['duration'])-8.0)>1e-6:
        raise RuntimeError(f'Tail is not an exact one-frame native rounding difference: {native}')
    backup=path.parent/'pre_normalization.mp4'
    original_receipt=path.parent/'original_mux_receipt.json'
    if not backup.exists(): shutil.copy2(output,backup)
    if not original_receipt.exists(): shutil.copy2(path,original_receipt)
    data.update(mux(native,inputs[data['product']],path.parent))
    data['native_frames']=200
    data['pre_normalization_video_sha256']=sha(backup)
    data['original_mux_receipt']=str(original_receipt)
    temp=path.with_suffix('.normalizing.json')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');temp.replace(path)
    print(f"Normalized {data['engine']}/{data['product']}: held real native last frame for 40ms",flush=True)
