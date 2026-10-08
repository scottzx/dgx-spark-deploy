#!/usr/bin/env python3
"""Measure decoded-frame switch artifacts and build a synchronized visual review."""
import hashlib
import html
import json
from pathlib import Path
import subprocess
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[3]/'docs/benchmarks/12_coca_cola_handheld'
A=ROOT/'actions';OUT=A/'transition_review';OUT.mkdir(exist_ok=True)
FF='/opt/homebrew/bin/ffmpeg'
CASES=[('original','原味'),('diet','健怡'),('zero','零度')]

def decode(path,crop):
    width,height,x,y=crop
    result=subprocess.run([FF,'-v','error','-i',str(path),'-vf',f'crop={width}:{height}:{x}:{y}',
                           '-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],
                          check=True,capture_output=True)
    pixels=np.frombuffer(result.stdout,dtype=np.uint8).reshape(-1,height,width,3)
    assert len(pixels)==201
    return pixels

records=[];cards=[];font=ImageFont.truetype('/System/Library/Fonts/Hiragino Sans GB.ttc',16)
for name,label in CASES:
    old=A/'voices/serena_hardcuts/dubbed'/name/'dubbed.mp4'
    new=A/'dubbed'/name/'dubbed.mp4';motion=A/'motion'/name/'motion.mp4'
    metrics=json.loads((new.parent/'metrics.json').read_text())
    assert metrics['transition_mode']=='smooth'
    voice=next(row for row in json.loads((A/'inputs/voice.json').read_text())['clips'] if row['product']==name)
    assert metrics['input_audio_sha256']==hashlib.sha256((A/'inputs'/f'{name}.wav').read_bytes()).hexdigest()
    weights=np.asarray(metrics['transition_weights'])
    assert len(weights)==201 and weights[0]==weights[-1]==0 and np.max(np.abs(np.diff(weights)))<.13
    times=np.arange(201)/25
    assert np.all(weights[(times>=voice['narration_starts_seconds'])&(times<=voice['narration_ends_seconds'])]==1)
    crop=(144,84,310,126)
    base=decode(motion,crop).astype(np.float32)
    before=decode(old,crop).astype(np.float32)-base
    after=decode(new,crop).astype(np.float32)-base
    old_delta=np.mean(np.abs(np.diff(before,axis=0)),axis=(1,2,3))
    new_delta=np.mean(np.abs(np.diff(after,axis=0)),axis=(1,2,3))
    transitions=[]
    for frame,description in [(55,'previous hard switch into lips'),(151,'previous hard switch out of lips')]:
        previous=float(old_delta[frame-1]);current=float(new_delta[frame-1])
        assert current<previous,(name,frame,previous,current)
        transitions.append({'boundary_frame':frame,'time_seconds':frame/25,'description':description,
                            'before_residual_step_mae':previous,'after_residual_step_mae':current,
                            'reduction_percent':100*(1-current/previous)})
    records.append({'product':name,'narration_start_seconds':metrics['narration_starts_seconds'],
                    'narration_end_seconds':metrics['narration_ends_seconds'],
                    'transition_seconds':metrics['transition_seconds'],'old_boundaries':transitions,
                    'final_fade_active_seconds':metrics['dubbing_window_seconds'],
                    'audio_hash_unchanged':True,'weights_continuous':True})
    indices=[52,53,54,55,56,57,148,149,150,151,152,153]
    crops=[decode(old,(220,220,274,38)),decode(new,(220,220,274,38))]
    grid=Image.new('RGB',(1320,992),'#f6f4ef');draw=ImageDraw.Draw(grid)
    for source,frames in enumerate(crops):
        for index,frame in enumerate(indices):
            x=index%6*220;y=(index//6*2+source)*248
            grid.paste(Image.fromarray(frames[frame]),(x,y))
            draw.text((x+4,y+222),f'{"修复前" if source==0 else "修复后"} {frame/25:.2f}s',font=font,fill='#222')
    grid.save(OUT/f'{name}_comparison.jpg',quality=95)
    version=hashlib.sha256(new.read_bytes()).hexdigest()[:12]
    end=metrics['narration_ends_seconds']
    cards.append(f'''<section data-end="{end}"><h2>{label}</h2><p>说话时段 2.40–{end:.2f} 秒。两版使用相同声音和动作底片。</p><div class="pair"><div><h3>修复前</h3><video controls muted playsinline preload="metadata" src="../voices/serena_hardcuts/dubbed/{name}/dubbed.mp4"></video></div><div><h3>修复后</h3><video controls muted playsinline preload="metadata" src="../dubbed/{name}/dubbed.mp4?v={version}"></video></div></div><p><button data-start="1.6">同步看开口</button> <button data-start="{end-.5}">同步看收口</button> <button data-pause>暂停</button> <a href="{name}_comparison.jpg">相邻帧放大对照</a></p></section>''')

receipt={'policy':'Decoded lower-face ROI (310,126,144,84). Subtract each same-index motion-source frame, then measure the adjacent-frame absolute change of that processing residual. 8-bit RGB MAE is a diagnostic for the former hard switches, not a universal aesthetic, identity or lip-sync score.',
         'all_six_previous_boundaries_improved':True,'clips':records}
(OUT/'verification.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>口型过渡 · 修复前后</title><style>*{box-sizing:border-box}body{margin:0;background:#f7f4ee;color:#25211f;font:16px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1300px;margin:auto;padding:24px}section{margin:24px 0;padding:20px;border:1px solid #e5ded5;border-radius:12px;background:white}.pair{display:grid;grid-template-columns:1fr 1fr;gap:18px}video{width:100%;background:#222}a{color:#b01e27}button{padding:9px 14px;border:1px solid #d3c7b9;background:#f7f4ee;border-radius:6px;cursor:pointer}h3{margin:8px 0}@media(max-width:700px){.pair{grid-template-columns:1fr}main{padding:12px}}</style><main><a href="../../review.html">返回完整视频</a><h1>开口、收口的过渡修复</h1><p>修复前在 2.2 秒和 6.04 秒附近直接切换口型画面；修复后按实际说话时段渐入、渐出，并保留嘴部周围的原始脸部画面。声音与三组商品动作保持一致。对比视频默认静音，可使用按钮同步播放。</p>CARDS<p><a href="verification.json">逐帧测量记录</a></p></main><script>for(const section of document.querySelectorAll('section')){const videos=[...section.querySelectorAll('video')];let timer;for(const button of section.querySelectorAll('button'))button.onclick=async()=>{clearTimeout(timer);videos.forEach(v=>v.pause());if(button.hasAttribute('data-pause'))return;const start=Number(button.dataset.start);for(const v of videos){v.currentTime=start;v.muted=true;}await Promise.all(videos.map(v=>v.play()));timer=setTimeout(()=>videos.forEach(v=>v.pause()),3200);};}</script></html>'''
(OUT/'review.html').write_text(page.replace('CARDS',''.join(cards)))
print(json.dumps([{'product':row['product'],'reductions_percent':[round(edge['reduction_percent'],1) for edge in row['old_boundaries']]} for row in records],ensure_ascii=False))
