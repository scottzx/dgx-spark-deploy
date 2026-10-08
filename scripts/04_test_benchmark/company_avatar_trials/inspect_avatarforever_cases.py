"""Export real speech and object-action frames for Avatar-Forever variants."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]/'docs/benchmarks/14_company_avatar_comparison'
count = 0
for engine in ['avatarforever','avatarforever_nocache','avatarforever_speaking']:
    for product in ['original','diet','zero']:
        folder = ROOT/'results'/engine/product
        video = folder/'video.mp4'
        if not video.exists():
            continue
        target = folder/'active_speech_faces.jpg'
        if not target.exists() or target.stat().st_mtime < video.stat().st_mtime:
            graph = 'select=between(n\\,64\\,116)*not(mod(n-64\\,4)),crop=128:128:320:80,scale=256:256:flags=bilinear,tile=7x2:padding=4'
            subprocess.run(['ffmpeg','-v','error','-y','-i',str(video),'-vf',graph,'-frames:v','1',str(target)],check=True)
        for timing in [.8,1.6,2.4,4,5.6,8]:
            target = folder/f'phase_{timing:g}.jpg'
            if not target.exists() or target.stat().st_mtime < video.stat().st_mtime:
                subprocess.run(['ffmpeg','-v','error','-y','-ss',str(timing),'-i',str(ROOT/'baseline'/f'{product}.mp4'),
                                '-ss',str(timing),'-i',str(video),'-filter_complex',
                                '[0:v]scale=384:256[a];[1:v]scale=384:256[b];[a][b]vstack',
                                '-frames:v','1',str(target)],check=True)
        count += 1
print('Avatar-Forever actual-frame inspection sets:',count)
