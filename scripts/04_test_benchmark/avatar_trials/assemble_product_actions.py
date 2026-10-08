#!/usr/bin/env python3
"""Build the complete pickup/presentation/put-back review and decoding evidence."""
import json
import hashlib
import shutil
from pathlib import Path
import subprocess

from PIL import Image,ImageDraw,ImageFont
import numpy as np

ROOT=Path(__file__).resolve().parents[3]/'docs/benchmarks/12_coca_cola_handheld'
A=ROOT/'actions';FF='/opt/homebrew/bin/ffmpeg';PROBE='/opt/homebrew/bin/ffprobe'
CASES=[('original','原味'),('diet','健怡'),('zero','零度')]

def run(args,**kw):return subprocess.run(args,check=True,**kw)

def get_frame(path,t):
    pixels=run([FF,'-v','error','-ss',str(t),'-i',str(path),'-frames:v','1','-vf','scale=384:256','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True).stdout
    return Image.fromarray(np.frombuffer(pixels,dtype=np.uint8).reshape(256,384,3))

def main():
    voice=json.loads((A/'inputs/voice.json').read_text()) if (A/'inputs/voice.json').exists() else None
    clips=[A/'dubbed'/name/'dubbed.mp4' for name,_ in CASES]
    args=[FF,'-v','error','-y']
    for clip in clips:args+=['-i',str(clip)]
    filters=';'.join(f'[{i}:v]trim=end_frame=201,setpts=PTS-STARTPTS[v{i}];[{i}:a]atrim=duration=8.04,asetpts=PTS-STARTPTS[a{i}]' for i in range(3))
    filters+=';'+''.join(f'[v{i}][a{i}]' for i in range(3))+'concat=n=3:v=1:a=1[v][a]'
    final=A/'three_products.mp4'
    run(args+['-filter_complex',filters,'-map','[v]','-map','[a]','-t','24.12','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(final)])
    if voice and voice['profile']=='serena_soft':
        shutil.copy2(final,A/'three_products_serena.mp4')
    version=hashlib.sha256(final.read_bytes()).hexdigest()[:12]
    get_frame(final,3).save(A/'poster.jpg',quality=94)
    font=ImageFont.truetype('/System/Library/Fonts/Hiragino Sans GB.ttc',18)
    data=[];cards=[];verified=[]
    for name,label in CASES:
        target=A/'dubbed'/name
        image=Image.new('RGB',(3*384,3*286),'#f6f4ef');draw=ImageDraw.Draw(image)
        for index,t in enumerate([0,.8,1.6,2.56,4,5.44,6.2,7.2,8]):
            x=(index%3)*384;y=(index//3)*286
            image.paste(get_frame(target/'dubbed.mp4',t),(x,y));draw.text((x+8,y+259),f'{label} · {t:.2f}s',font=font,fill='#222')
        image.save(target/'contact.jpg',quality=96)
        get_frame(target/'dubbed.mp4',3).save(target/'poster.jpg',quality=94)
        m=json.loads((A/'motion'/name/'metrics.json').read_text());d=json.loads((target/'metrics.json').read_text())
        data.append({'product':name,'motion':m,'dubbing':{k:v for k,v in d.items() if k not in ['face_boxes','raw_face_boxes','transition_weights']}})
        cards.append(f'<article><h2>{label} · 完整过程</h2><video controls playsinline preload="metadata" poster="actions/dubbed/{name}/poster.jpg?v={version}" src="actions/dubbed/{name}/dubbed.mp4?v={version}"></video><p><a href="actions/dubbed/{name}/dubbed.mp4?v={version}" download>下载口播片</a> · <a href="actions/motion/{name}/motion.mp4">动作原片</a> · <a href="actions/dubbed/{name}/contact.jpg?v={version}">逐步帧对照</a></p></article>')
    for path in clips+[A/'motion'/name/'motion.mp4' for name,_ in CASES]+[final]:
        p=json.loads(run([PROBE,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True).stdout)
        v=next(s for s in p['streams'] if s['codec_type']=='video');n=603 if path==final else 201
        assert int(v['nb_read_frames'])==n and abs(float(v['duration'])-n/25)<.01
        run([FF,'-v','error','-i',str(path),'-f','null','-'],capture_output=True)
        row={'file':str(path.relative_to(ROOT)),'frames':n,'fps':25,'video_duration_seconds':float(v['duration']),'full_decode_passed':True}
        audio=next((s for s in p['streams'] if s['codec_type']=='audio'),None)
        if audio:
            assert abs(float(audio['duration'])-n/25)<.08
            row['audio_duration_seconds']=float(audio['duration'])
        verified.append(row)
    (A/'metrics.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    smooth=all(item['dubbing'].get('transition_mode')=='smooth' for item in data)
    if smooth:shutil.copy2(final,A/'three_products_serena_smooth.mp4')
    (A/'verification.json').write_text(json.dumps(verified,ensure_ascii=False,indent=2)+'\n')
    qa=json.loads((A/'qa.json').read_text()) if (A/'qa.json').exists() else {'summary':'待逐帧验收，生成与解码成功不能代替动作验收。'}
    import html
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>三罐商品 · 拿起、介绍、放回</title><style>*{box-sizing:border-box}body{margin:0;background:#f7f4ee;color:#25211f;font:16px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1400px;margin:auto;padding:36px}h1{font-size:34px;margin:8px 0}h2{font-size:18px}.muted{color:#736b64}.film{max-width:1020px;margin:auto}.film video{width:100%;background:#222;border-radius:14px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}article,.panel{background:white;border-radius:14px;border:1px solid #e5ded5;padding:20px;margin:20px 0}article video{width:100%;border-radius:8px;background:#ddd}a{color:#b01e27}.steps{display:flex;gap:14px;margin:16px 0;flex-wrap:wrap}.steps span{background:#ede7dd;border-radius:6px;padding:8px 14px}.result{border-left:4px solid #c5222b;padding-left:14px}.inputs{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.inputs img{width:100%;border-radius:8px}.inputs figure{margin:0}.inputs figcaption{font-size:14px}@media(max-width:850px){main{padding:18px}h1{font-size:27px}.grid{grid-template-columns:1fr}.inputs{grid-template-columns:repeat(2,minmax(0,1fr))}}</style><main><p class="muted">DGX Spark / GB10 · 全部本地推理 · 2026-10-07</p><h1>三罐商品：拿起 → 介绍 → 放回</h1><p>原味、健怡、零度依次演示。每罐 8.04 秒，每罐内部为连续生成镜头，三罐之间剪辑衔接，共 24.12 秒。</p><div class="steps"><span>0–2.4s · 抓取并举起</span><span>2.4–5.8s · 手持介绍</span><span>5.8–8.04s · 放回并松手</span></div><p class="result">QA</p><section class="film"><video controls playsinline preload="metadata" poster="actions/poster.jpg" src="actions/three_products.mp4"></video><p><a href="actions/three_products.mp4" download>下载三组完整视频</a> · <a href="README.md">测试结果与架构判断</a> · <a href="OPEN_SOURCE_RESEARCH.md">其他开源方案</a></p></section><section class="grid">CARDS</section><section class="panel"><h2>动作条件与验收</h2><p>本地 Qwen-Image 生成共同桌面画面和三个手持关键帧；LTX-2.5 使用首帧、2.56s／5.44s 手持关键帧、末帧条件生成连续动作；MuseTalk 按原视频逐帧输入对齐介绍时段的嘴部。原始中文配音在 2.4s 开始。</p><p>动作不是静态图切换，也没有倒放拿起镜头来冒充放回。末帧条件只约束终态，中间抓取、商品身份、接触与松手仍需看逐步帧对照。关键帧和商品文字可能存在生成误差。</p><div class="inputs">INPUTS</div><p><a href="actions/metrics.json">动作与配音测量</a> · <a href="actions/verification.json">完整解码与时长检查</a> · <a href="actions/qa.json">逐组验收记录</a> · <a href="held_baseline.html">A/B/C 固定手持基线</a></p></section></main></html>'''
    inputs='<figure><img src="actions/inputs/table.png" alt="三罐商品放在桌上"><figcaption>起止画面 · 三罐均在桌上</figcaption></figure>'
    inputs+=''.join(f'<figure><img src="actions/inputs/{"zero_held_v2" if name=="zero" else name+"_held"}.png" alt="手持{label}关键帧"><figcaption>{label} · 手持关键帧</figcaption></figure>' for name,label in CASES)
    voice_line=''
    if voice:
        voice_line='<p>配音已更新为 <strong>Serena 柔和女声</strong>，语气平稳、亲切，降低高频和整体响度，并重新对齐口型。<a href="actions/voices/vivian/three_products.mp4">对比原版配音视频</a></p>'
        voice_line+=f'<p>试听三段配音：</p><audio controls preload="metadata" src="actions/inputs/voice_preview.wav?v={version}"></audio>'
    if smooth:
        voice_line+='<p>开口与收口已改为平滑过渡。<a href="actions/transition_review/review.html">查看修复前后对比</a></p>'
    page=page.replace('<section class="film">',voice_line+'<section class="film">')
    page=page.replace('poster="actions/poster.jpg" src="actions/three_products.mp4"',f'poster="actions/poster.jpg?v={version}" src="actions/three_products.mp4?v={version}"')
    page=page.replace('href="actions/three_products.mp4"',f'href="actions/three_products.mp4?v={version}"')
    page=page.replace('原始中文配音在 2.4s 开始。','中文配音在 2.4s 开始。')
    (ROOT/'review.html').write_text(page.replace('CARDS',''.join(cards)).replace('INPUTS',inputs).replace('QA',html.escape(qa['summary'])))
    print(json.dumps({'verified_media':len(verified),'frames':603,'duration_seconds':24.12,'output':str(final)},ensure_ascii=False))

if __name__=='__main__':main()
