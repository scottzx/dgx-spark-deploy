#!/usr/bin/env python3
"""Assemble local handheld comparison, frame evidence, and media verification."""
import hashlib
import html
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[3]/'docs/benchmarks/12_coca_cola_handheld'
FFMPEG='/opt/homebrew/bin/ffmpeg'
FFPROBE='/opt/homebrew/bin/ffprobe'
PRODUCTS=[('original','原味'),('diet','健怡'),('zero','零度')]
NAMES={'A':'LiveTalking · MuseTalk 1.5','B':'OpenAvatarChat · FlashHead Lite','C':'EchoMimicV3 Flash'}
FONT='/System/Library/Fonts/Hiragino Sans GB.ttc'

def run(args,**kwargs):
    return subprocess.run(args,check=True,**kwargs)

def frame(path,seconds):
    data=run([FFMPEG,'-v','error','-ss',str(seconds),'-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-vf','scale=512:512','pipe:1'],capture_output=True).stdout
    return Image.fromarray(np.frombuffer(data,dtype=np.uint8).reshape(512,512,3))

def main():
    measurements=[];verification=[];cards=[];table=[]
    font=ImageFont.truetype(FONT,17)
    for route in NAMES:
        target=ROOT/f'route_{route}';target.mkdir(exist_ok=True)
        clips=[ROOT/f'handheld_{route}_{name}/raw.mp4' for name,_ in PRODUCTS]
        rows=[]
        for name,_ in PRODUCTS:
            m=json.loads((ROOT/f'handheld_{route}_{name}/metrics.json').read_text())
            m['product']=name;rows.append(m)
        generation=sum(m.get('render_and_write_seconds',m.get('generation_seconds',0)) for m in rows)
        audio_features=sum(m.get('audio_feature_seconds',0) for m in rows)
        loading=sum(m.get('load_and_avatar_prepare_seconds',m.get('load_and_prepare_seconds',0)) for m in rows)
        measurement={'route':route,'engine':NAMES[route],'frames':291,'duration_seconds':11.64,
                     'generation_seconds':generation,'audio_feature_seconds':audio_features,
                     'generation_fps':291/generation,'load_and_prepare_seconds_total_for_three_processes':loading,
                     'peak_cuda_allocated_gib':max(m['peak_cuda_allocated_gib'] for m in rows),'shots':rows}
        measurements.append(measurement)
        args=[FFMPEG,'-v','error','-y']
        for clip in clips:args+=['-i',str(clip)]
        filters=';'.join(f'[{i}:v]trim=end_frame=97,scale=768:768:flags=lanczos,setsar=1,setpts=PTS-STARTPTS[v{i}];[{i}:a]atrim=duration=3.88,aresample=24000,asetpts=PTS-STARTPTS[a{i}]' for i in range(3))
        filters+=';'+''.join(f'[v{i}][a{i}]' for i in range(3))+'concat=n=3:v=1:a=1[v][a]'
        output=target/'handheld.mp4'
        run(args+['-filter_complex',filters,'-map','[v]','-map','[a]','-t','11.64','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(output)])
        frame(output,1).save(target/'poster.jpg',quality=93)
        sheet=Image.new('RGB',(5*256,3*290),'#f8f6f3');draw=ImageDraw.Draw(sheet)
        for row,(name,label) in enumerate(PRODUCTS):
            reference=Image.open(ROOT/'inputs'/f'{name}.png').convert('RGB').resize((256,256))
            sheet.paste(reference,(0,row*290));draw.text((8,row*290+260),f'{label} · 输入',font=font,fill='#222')
            for col,t in enumerate([0,1,2,3.8],start=1):
                shot=frame(ROOT/f'handheld_{route}_{name}/raw.mp4',t)
                sheet.paste(shot.resize((256,256)),(col*256,row*290))
                draw.text((col*256+8,row*290+260),f'{route} · {t:.1f}s',font=font,fill='#222')
        sheet.save(target/'contact.jpg',quality=95)
        for clip in clips+[output]:
            probe=json.loads(run([FFPROBE,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(clip)],capture_output=True,text=True).stdout)
            run([FFMPEG,'-v','error','-i',str(clip),'-f','null','-'],capture_output=True)
            streams={s['codec_type']:s for s in probe['streams']}
            expected=291 if clip==output else 97
            assert int(streams['video']['nb_read_frames'])==expected
            assert abs(float(streams['video']['duration'])-expected/25)<.01
            assert abs(float(streams['audio']['duration'])-expected/25)<.08
            pcm=run([FFMPEG,'-v','error','-i',str(clip),'-map','0:a','-f','s16le','-ar','24000','-ac','1','pipe:1'],capture_output=True).stdout
            verification.append({'file':str(clip.relative_to(ROOT)),'frames':expected,'video_seconds':float(streams['video']['duration']),
                                 'audio_seconds':float(streams['audio']['duration']),'full_decode_passed':True,'decoded_audio_sha256':hashlib.sha256(pcm).hexdigest()})
        cards.append(f'''<article><h2><b>{route}</b> {html.escape(NAMES[route])}</h2><video controls playsinline preload="metadata" {'muted' if route!='A' else ''} poster="route_{route}/poster.jpg" src="route_{route}/handheld.mp4"></video><p>{generation:.2f} 秒生成 · {291/generation:.2f} FPS · {measurement['peak_cuda_allocated_gib']:.2f} GiB CUDA 峰值</p><p><a href="route_{route}/handheld.mp4" download>下载视频</a> · <a href="route_{route}/contact.jpg">输入与逐秒帧对照</a></p></article>''')
        table.append(f'<tr><td>{route} · {html.escape(NAMES[route])}</td><td>{generation:.2f}s</td><td>{291/generation:.2f}</td><td>{loading:.2f}s</td><td>{measurement["peak_cuda_allocated_gib"]:.2f}</td></tr>')
    for index in range(3):
        hashes={v['decoded_audio_sha256'] for v in verification if v['file'].startswith('handheld_') and PRODUCTS[index][0] in v['file']}
        assert len(hashes)==1,'Each SKU must use the same decoded audio across routes'
    (ROOT/'comparison_metrics.json').write_text(json.dumps(measurements,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'verification.json').write_text(json.dumps({'media':verification,'identical_decoded_audio_per_sku':True},ensure_ascii=False,indent=2)+'\n')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>人物手持可口可乐 · 本地实测</title><style>*{box-sizing:border-box}body{margin:0;background:#f6f4ef;color:#242220;font:16px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1500px;margin:auto;padding:36px}h1{font-size:34px;margin:10px 0}h2{font-size:16px}h2 b{display:inline-block;background:#c92129;color:white;padding:2px 12px;border-radius:6px;margin-right:5px}.muted{color:#68625c}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}article,.panel{background:white;border:1px solid #e5dfd6;border-radius:16px;padding:18px}video{width:100%;aspect-ratio:1;background:#ddd;border-radius:8px}button{border:0;border-radius:8px;padding:11px 18px;background:#c92129;color:white;cursor:pointer;margin:12px 8px 20px 0}a{color:#ac1924}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:10px;border-bottom:1px solid #eee}.panel{margin-top:24px}.inputs{display:flex;gap:16px}.inputs figure{margin:0;max-width:220px}.inputs img{width:100%;border-radius:8px}#status{font-size:14px;color:#68625c}.notice{border-left:4px solid #c92129;padding-left:14px}@media(max-width:850px){main{padding:18px}.grid{grid-template-columns:1fr}.panel{overflow:auto}h1{font-size:27px}}</style><main><p class="muted">DGX Spark / GB10 · 2026-10-07 · 本地生成</p><h1>人物手持商品介绍</h1><p>同一位主播、同一份手持参考图、同一段中文音频。依次展示原味、健怡、零度，每罐 3.88 秒，合计 11.64 秒。</p><p class="notice">先看手与罐身的接触、标签变化，再看表情与口型。A 修改嘴部，B/C 会生成画面运动。每罐都是独立测试镜头，换罐处为明确剪辑，未测试连续拿起或更换商品。</p><button id="play">同步播放</button><button id="pause">暂停</button><button id="restart">回到开头</button><span id="status">播放时只保留 A 的声音</span><section class="grid">CARDS</section><section class="panel"><h2>共同输入 · 三种手持照片</h2><div class="inputs">INPUTS</div><p class="muted">本地 Qwen-Image-2.1 + 六步 LoRA，根据上一轮主播和官网商品图生成；商品进入模型画面，无独立商品图层。包装细节可能在输入阶段就已变化，需与官网参考图区分。</p></section><section class="panel"><h2>这一轮测量</h2><table><thead><tr><th>路线</th><th>11.64秒生成</th><th>有效 FPS</th><th>三次加载与准备</th><th>CUDA 峰值 GiB</th></tr></thead><tbody>ROWS</tbody></table><p class="muted">A 为合成与写帧耗时，音频特征提取另记；B 包含缓冲与流式输出队列；C 包含生成与写帧。未计入素材生成、TTS、模型加载、最终编码。短样本、未做长期直播或 WebRTC 测试；不同路线原片分辨率不同，不能据此宣称生产级实时性能。</p><p><a href="README.md">实测判断与架构建议</a> · <a href="comparison_metrics.json">原始测量</a> · <a href="verification.json">媒体校验</a></p></section></main><script>const vs=[...document.querySelectorAll('video')],s=document.querySelector('#status');document.querySelector('#play').onclick=async()=>{const t=vs[0].currentTime;vs.forEach((v,i)=>{v.currentTime=t;v.muted=i!==0});try{await Promise.all(vs.map(v=>v.play()));s.textContent='三条同步播放 · A 有声'}catch(e){s.textContent='请点击单个视频播放按钮'}};document.querySelector('#pause').onclick=()=>vs.forEach(v=>v.pause());document.querySelector('#restart').onclick=()=>vs.forEach(v=>{v.pause();v.currentTime=0});vs[0].addEventListener('timeupdate',()=>{if(vs[0].paused)return;vs.slice(1).forEach(v=>{if(v.readyState>=2&&Math.abs(v.currentTime-vs[0].currentTime)>.1)v.currentTime=vs[0].currentTime})});</script></html>'''
    input_cards=''.join(f'<figure><a href="inputs/{name}.png"><img src="inputs/{name}.png" alt="主播手持{label}"></a><figcaption>{label}</figcaption></figure>' for name,label in PRODUCTS)
    (ROOT/'held_baseline.html').write_text(page.replace('CARDS','\n'.join(cards)).replace('ROWS','\n'.join(table)).replace('INPUTS',input_cards))
    print(json.dumps({'routes':[{k:v for k,v in m.items() if k!='shots'} for m in measurements],'verified_media':len(verification)},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
