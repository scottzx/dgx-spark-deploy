#!/usr/bin/env python3
"""Assemble Wan product videos, compare their drivers, and verify media/timing."""
import hashlib
from functools import lru_cache
from fractions import Fraction
import html
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[3]/'docs/benchmarks/13_wan_animate2_product_actions'
PREVIOUS=ROOT.parent/'12_coca_cola_handheld'/'actions'
FF='/opt/homebrew/bin/ffmpeg';PROBE='/opt/homebrew/bin/ffprobe'
CASES=[('original','原味'),('diet','健怡'),('zero','零度')]
FONT=ImageFont.truetype('/System/Library/Fonts/Hiragino Sans GB.ttc',15)

def run(args):return subprocess.run(args,check=True,capture_output=True)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
@lru_cache(maxsize=32)
def probe_video(path):
    return json.loads(run([PROBE,'-v','error','-count_frames','-show_streams','-of','json',str(path)]).stdout)
def frame(path,t):
    video=next(s for s in probe_video(path)['streams'] if s['codec_type']=='video')
    t=min(t,float(video['duration'])-1/float(Fraction(video['avg_frame_rate']))-.0001)
    data=run([FF,'-v','error','-ss',str(t),'-i',str(path),'-frames:v','1','-vf','scale=256:170',
              '-f','rawvideo','-pix_fmt','rgb24','pipe:1']).stdout
    return Image.fromarray(np.frombuffer(data,dtype=np.uint8).reshape(170,256,3))
def decode_crop(path,box):
    x,y,w,h=box
    data=run([FF,'-v','error','-i',str(path),'-vf',f'crop={w}:{h}:{x}:{y}',
              '-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','pipe:1']).stdout
    return np.frombuffer(data,dtype=np.uint8).reshape(-1,h,w,3).astype(np.float32)

def main():
    (ROOT/'baseline').mkdir(exist_ok=True)
    voice=json.loads((ROOT/'voice'/'voice.json').read_text())
    qa=json.loads((ROOT/'qa.json').read_text()) if (ROOT/'qa.json').exists() else {'summary':'视频已生成，动作、包装与连续性等待人工帧对照。'}
    paths=[];cards=[];metrics=[];timing=[]
    for name,label in CASES:
        driver=ROOT/'inputs'/f'{name}_driver.mp4';native=ROOT/'motion'/name/'motion.mp4'
        normalized=ROOT/'motion_25'/name/'motion.mp4';dub=ROOT/'dubbed'/name/'dubbed.mp4'
        baseline=ROOT/'baseline'/f'{name}.mp4';shutil.copy2(PREVIOUS/'dubbed'/name/'dubbed.mp4',baseline)
        paths.extend([(driver,201,25),(native,192,24),(normalized,201,25),(dub,201,25),(baseline,201,25)])
        motion=json.loads((native.parent/'metrics.json').read_text());dubbing=json.loads((dub.parent/'metrics.json').read_text())
        assert motion['driving_sha256']==digest(driver) and motion['reference_sha256']==digest(ROOT/'inputs/reference.png')
        assert motion['output_sha256']==digest(native) and dubbing['input_video_sha256']==digest(normalized)
        assert dubbing['transition_mode']=='smooth' and dubbing['speaker']=='Serena'
        assert dubbing['input_audio_sha256']==digest(ROOT/'voice'/f'{name}.wav')
        weights=np.asarray(dubbing['transition_weights']);times=np.arange(201)/25
        speech=next(row for row in voice['clips'] if row['product']==name)
        assert len(weights)==201 and weights[0]==weights[-1]==0 and np.max(np.abs(np.diff(weights)))<.13
        assert np.all(weights[(times>=speech['narration_starts_seconds'])&(times<=speech['narration_ends_seconds'])]==1)
        image=Image.new('RGB',(9*256,3*198),'#f6f4ef');draw=ImageDraw.Draw(image)
        sample_times=[0,.8,1.6,2.56,4,5.44,6.2,7.2,8]
        for row,(path,description) in enumerate([(driver,'动作参照'),(native,'Wan 动作'),(dub,'Wan 口播')]):
            for column,t in enumerate(sample_times):
                image.paste(frame(path,t),(column*256,row*198))
                draw.text((column*256+6,row*198+172),f'{description} · {t:.2f}s',font=FONT,fill='#222')
        image.save(dub.parent/'contact.jpg',quality=95)
        frame(dub,3).save(dub.parent/'poster.jpg',quality=95)
        # Dubbing residual measures its processing changes separately from the Wan motion.
        b=np.median(np.asarray(dubbing['face_boxes']),axis=0).astype(int)
        x1,y1,x2,y2=b;crop=(x1,max(y1,0),x2-x1,y2-y1)
        base=decode_crop(normalized,crop);processed=decode_crop(dub,crop)
        assert len(base)==len(processed)==201
        residual_delta=np.mean(np.abs(np.diff(processed-base,axis=0)),axis=(1,2,3))
        motion_delta=np.mean(np.abs(np.diff(base,axis=0)),axis=(1,2,3))
        edges=[]
        for t,description in [(2.2,'旧开口硬切点'),(6.04,'旧收口硬切点'),(speech['narration_starts_seconds'],'本轮开口'),
                               (speech['narration_ends_seconds'],'本轮收口'),(81/24,'Wan 第二段首帧'),(161/24,'Wan 第三段首帧')]:
            i=round(t*25);near=motion_delta[max(0,i-6):min(200,i+5)];median=float(np.median(near))
            edges.append({'time_seconds':t,'description':description,'nearest_frame':i,
                          'dubbing_residual_step_mae':float(residual_delta[i-1]),
                          'motion_face_step_mae':float(motion_delta[i-1]),
                          'motion_step_ratio_to_local_median':float(motion_delta[i-1])/max(median,.0001)})
        timing.append({'product':name,'audio_hash_unchanged':True,'transition_weights_continuous':True,'face_crop':list(map(int,crop)),'boundaries':edges})
        closeup=Image.new('RGB',(6*200,4*246),'#f6f4ef');close_draw=ImageDraw.Draw(closeup)
        for boundary,t in enumerate([speech['narration_starts_seconds'],speech['narration_ends_seconds']]):
            for row,(pixels,description) in enumerate([(base,'Wan 动作'),(processed,'Wan 口型')]):
                for column,i in enumerate(range(round(t*25)-3,round(t*25)+3)):
                    position=(column*200,(boundary*2+row)*246)
                    closeup.paste(Image.fromarray(pixels[i].astype(np.uint8)).resize((200,220)),position)
                    close_draw.text((position[0]+5,position[1]+222),f'{description} {i/25:.2f}s',font=FONT,fill='#222')
        closeup.save(dub.parent/'speech_boundaries.jpg',quality=95)
        joins=Image.new('RGB',(6*256,2*198),'#f6f4ef');join_draw=ImageDraw.Draw(joins)
        for row,first in enumerate([81,161]):
            for column,i in enumerate(range(first-3,first+3)):
                joins.paste(frame(native,i/24),(column*256,row*198))
                join_draw.text((column*256+5,row*198+172),f'Wan 原片 {i/24:.3f}s',font=FONT,fill='#222')
        joins.save(dub.parent/'segment_boundaries.jpg',quality=95)
        metrics.append({'product':name,'motion':motion,'dubbing':{k:v for k,v in dubbing.items() if k not in ['face_boxes','raw_face_boxes','transition_weights']}})
        version=digest(dub)[:12]
        cards.append(f'''<section class="case"><h2>{label} · 拿起、介绍、放回</h2><div class="pair"><div><h3>上一版 · LTX＋柔和配音</h3><video controls playsinline preload="metadata" src="baseline/{name}.mp4"></video></div><div><h3>本轮 · Wan＋同一配音</h3><video controls playsinline preload="metadata" poster="dubbed/{name}/poster.jpg" src="dubbed/{name}/dubbed.mp4?v={version}"></video></div></div><p><button data-time="0">同步看完整过程</button> <button data-time="1.7">看开口</button> <button data-time="{speech['narration_ends_seconds']-.5:.3f}">看收口</button> <button data-stop>暂停</button></p><p><a href="dubbed/{name}/contact.jpg">三行逐步帧对照</a> · <a href="dubbed/{name}/speech_boundaries.jpg">开口/收口放大</a> · <a href="dubbed/{name}/segment_boundaries.jpg">Wan 段落交界</a> · <a href="motion/{name}/motion.mp4">Wan 动作原片</a> · <a href="inputs/{name}_driver.mp4">生成动作参照</a></p><details><summary>查看动作帧对照</summary><img src="dubbed/{name}/contact.jpg" alt="{label}输入、动作输出与口播输出"></details></section>''')
    final=ROOT/'three_products_wan_serena.mp4';args=[FF,'-v','error','-y']
    for name,_ in CASES:args+=['-i',str(ROOT/'dubbed'/name/'dubbed.mp4')]
    filters=';'.join(f'[{i}:v]trim=end_frame=201,setpts=PTS-STARTPTS[v{i}];[{i}:a]atrim=duration=8.04,asetpts=PTS-STARTPTS[a{i}]' for i in range(3))
    filters+=';[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][a]'
    run(args+['-filter_complex',filters,'-map','[v]','-map','[a]','-t','24.12','-c:v','libx264','-crf','18',
              '-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(final)])
    paths.append((final,603,25));verified=[]
    for path,n,fps in paths:
        probe=probe_video(path)
        v=next(s for s in probe['streams'] if s['codec_type']=='video')
        assert int(v['nb_read_frames'])==n and v['avg_frame_rate']==f'{fps}/1' and abs(float(v['duration'])-n/fps)<.01
        run([FF,'-v','error','-i',str(path),'-f','null','-'])
        audio=next((s for s in probe['streams'] if s['codec_type']=='audio'),None)
        if audio:assert abs(float(audio['duration'])-n/fps)<.08
        verified.append({'file':str(path.relative_to(ROOT)),'frames':n,'fps':fps,'size':[v['width'],v['height']],
                         'duration_seconds':float(v['duration']),'full_decode_passed':True,'sha256':digest(path)})
    (ROOT/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'verification.json').write_text(json.dumps(verified,indent=2)+'\n')
    (ROOT/'transition_diagnostics.json').write_text(json.dumps({'policy':'8-bit RGB adjacent-frame MAE in the median tracked face crop. A diagnostic, not a lip-sync, identity or aesthetic acceptance score. Native segment boundaries may land between 25 FPS frames.', 'clips':timing},ensure_ascii=False,indent=2)+'\n')
    version=digest(final)[:12];frame(final,3).save(ROOT/'poster.jpg',quality=95)
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Wan-Animate-2 · 三组商品动作测试</title><style>*{box-sizing:border-box}body{margin:0;background:#f7f4ee;color:#25211f;font:16px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1250px;margin:auto;padding:30px}h1{font-size:32px;margin:6px 0}h2{font-size:22px}h3{font-size:16px}a{color:#a7212b}.muted{color:#736b64}.result{border-left:4px solid #b3242c;padding:8px 16px;background:#fff}.film{max-width:960px;margin:24px auto}video{width:100%;background:#222;border-radius:10px}.case{background:#fff;border:1px solid #e5ded5;border-radius:14px;padding:20px;margin:22px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:18px}button{padding:9px 13px;margin:4px 5px 4px 0;background:#f7f4ee;border:1px solid #d3c7b9;border-radius:6px;cursor:pointer}details img{max-width:100%;margin-top:16px}footer{font-size:14px;color:#736b64}@media(max-width:750px){main{padding:16px}.pair{grid-template-columns:1fr}h1{font-size:26px}}</style><main><p class="muted">DGX Spark / GB10 · Wan-Animate-2 14B Distilled · 2026-10-08</p><h1>三组商品：生成动作参照 → Wan → 柔和口播</h1><p>原味、健怡、零度分别拿起、手持介绍、放回并松手。每组 8.04 秒，完整视频 24.12 秒。配音沿用 Serena，嘴部保留平滑渐入渐出。</p><p class="result">QA</p><section class="film"><video controls playsinline preload="metadata" poster="poster.jpg" src="three_products_wan_serena.mp4?v=VERSION"></video><p><a href="three_products_wan_serena.mp4?v=VERSION" download>下载完整测试片</a> · <a href="README.md">测试记录</a> · <a href="verification.json">解码验证</a></p></section>CARDS<footer><p>动作参照来自上一轮 LTX-2.5 生成视频，由用户授权复用。此轮没有实拍输入。Wan 重新生成整个画面，可能继承或新增手指、商品文字和罐体误差。</p><p>参照 768×512 / 25 FPS；Wan 目标面积 576×384 / 24 FPS，口播前转为 25 FPS。三组使用同一配音，不倒放动作。同步播放默认静音，可单独播放完整片听声音。</p><p><a href="inputs/sources.json">输入来源</a> · <a href="metrics.json">运行测量</a> · <a href="qa.json">人工验收</a> · <a href="transition_diagnostics.json">口型与段落交界诊断</a></p></footer></main><script>for(const section of document.querySelectorAll('.case')){const videos=[...section.querySelectorAll('video')];for(const button of section.querySelectorAll('button'))button.onclick=async()=>{videos.forEach(v=>v.pause());if(button.hasAttribute('data-stop'))return;for(const v of videos){v.currentTime=Number(button.dataset.time);v.muted=true;}await Promise.all(videos.map(v=>v.play()));};}</script></html>'''
    page=page.replace('完整视频 24.12 秒。','完整视频 24.12 秒，三组之间剪辑衔接。')
    (ROOT/'review.html').write_text(page.replace('QA',html.escape(qa['summary'])).replace('VERSION',version).replace('CARDS',''.join(cards)))
    print(json.dumps({'media_verified':len(verified),'final_frames':603,'final_duration_seconds':24.12,'output':str(final)},ensure_ascii=False))

if __name__=='__main__':main()
