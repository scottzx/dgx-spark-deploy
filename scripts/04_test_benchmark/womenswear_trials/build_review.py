"""Verify finished native results and render the shared portrait garment comparison."""
import argparse
import hashlib
import fcntl
import html
import json
from pathlib import Path
import subprocess
import tempfile
from PIL import Image, ImageDraw
import numpy as np

PROJECT=Path(__file__).resolve().parents[3]
parser=argparse.ArgumentParser()
parser.add_argument('--root',type=Path,default=PROJECT/'docs/benchmarks/15_womenswear_avatar_comparison')
args=parser.parse_args()
ROOT=args.root.resolve()
CASES=[('shirt','白色衬衫'),('cardigan','粉色针织开衫'),('dress','黑色连衣裙')]
ENGINES=[('latentsync','LTX＋LatentSync 1.6'),('longcat','LongCat-Video-Avatar 1.5'),('infinitetalk','InfiniteTalk')]
ROOT.mkdir(parents=True,exist_ok=True)
build_lock=(ROOT/'build.lock').open('w')
fcntl.flock(build_lock,fcntl.LOCK_EX)
previous={}
if (ROOT/'verification.json').exists():
    previous={r['path']:r for r in json.loads((ROOT/'verification.json').read_text())}
verification=[]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(path,text):
    temporary=path.with_name(path.name+'.writing')
    temporary.write_text(text)
    temporary.replace(path)
def verify(p,frames=201,audio=True):
    key=str(p.relative_to(ROOT));digest=sha(p)
    if key in previous and previous[key]['sha256']==digest:
        row=previous[key];verification.append(row);return row
    result=subprocess.run(['ffprobe','-v','error','-count_frames','-show_streams','-of','json',str(p)],capture_output=True,text=True,check=True)
    streams=json.loads(result.stdout)['streams'];v=next(s for s in streams if s['codec_type']=='video')
    has_audio=any(s['codec_type']=='audio' for s in streams)
    subprocess.run(['ffmpeg','-v','error','-i',str(p),'-f','null','-'],capture_output=True,check=True)
    row={'path':key,'sha256':digest,'frames':int(v['nb_read_frames']),'duration_seconds':float(v['duration']),
         'size':[v['width'],v['height']],'fps':v['avg_frame_rate'],'audio':has_audio,'full_decode':True}
    assert v['width']*4==v['height']*3,row
    assert row['fps']=='25/1',row
    if frames:assert row['frames']==frames and abs(row['duration_seconds']-frames/25)<.06,row
    if audio:assert has_audio,row
    verification.append(row);return row

def sheet(movie,folder,indices,name='action_frames.jpg',crop=None):
    indices=sorted(set(indices))
    target=folder/name
    if target.exists() and target.stat().st_mtime>=movie.stat().st_mtime:return
    with tempfile.TemporaryDirectory() as temp:
        selection='+'.join(f'eq(n\\,{i})' for i in indices)
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(movie),'-vf',f'select={selection}',
                        '-fps_mode','vfr',str(Path(temp)/'frame_%03d.png')],capture_output=True,check=True)
        files=sorted(Path(temp).glob('frame_*.png'));assert len(files)==len(indices),(movie,indices,len(files))
        columns=5 if crop else 3;cell_w=240;cell_h=240 if crop else 344
        canvas=Image.new('RGB',(columns*cell_w,((len(files)+columns-1)//columns)*cell_h),'#e8e6e0')
        draw=ImageDraw.Draw(canvas)
        for i,(p,frame) in enumerate(zip(files,indices)):
            with Image.open(p) as im:
                if crop:
                    w,h=im.size;im=im.crop(tuple(round(a*b) for a,b in zip(crop,[w,h,w,h])))
                im.thumbnail((cell_w,cell_h-25));x=(i%columns)*cell_w;y=(i//columns)*cell_h
                canvas.paste(im,(x+(cell_w-im.width)//2,y+25))
                draw.text((x+8,y+6),f'{frame/25:.2f}s | frame {frame}',fill='#222222')
        canvas.save(target,quality=94)

voice={}
if (ROOT/'inputs/voice.json').exists():voice=json.loads((ROOT/'inputs/voice.json').read_text())
natural=voice.get('profile')=='serena_default'
speech={r['product']:r for r in voice.get('clips',[])}
findings={}
if (ROOT/'quality_review.json').exists():
    findings=json.loads((ROOT/'quality_review.json').read_text()).get('cases',{})
data={'products':[],'routes':[{'key':e,'label':l} for e,l in ENGINES]}
measurements=[];audio_checks=[]
for key,label in CASES:
    product={'key':key,'label':label,'routes':{}}
    pcm_by_engine={}
    baseline=ROOT/'ltx'/key/'motion.mp4'
    if baseline.exists() and (baseline.parent/'metrics.json').exists():
        verify(baseline,audio=False);sheet(baseline,baseline.parent,[0,16,32,48,64,100,136,152,168,184,200])
    for engine,title in ENGINES:
        folder=ROOT/'results'/engine/key;video=folder/'video.mp4';metrics=folder/'metrics.json'
        if not video.exists() or not metrics.exists():continue
        m=json.loads(metrics.read_text());media=verify(video)
        assert media['sha256']==m['video_sha256'],str(video)
        native=folder/'native.mp4';native_media=verify(native,frames=None,audio=False)
        assert native_media['sha256']==m['native_output_sha256'],str(native)
        native_view=folder/'native_with_serena.mp4'
        view_receipt=folder/'native_playback.json'
        audio_source=ROOT/'inputs'/key/'audio.wav'
        view_inputs={'native_sha256':native_media['sha256'],'audio_sha256':sha(audio_source),
                     'duration_seconds':native_media['duration_seconds']}
        if not native_view.exists() or not view_receipt.exists() or json.loads(view_receipt.read_text()).get('inputs')!=view_inputs:
            subprocess.run(['ffmpeg','-v','error','-y','-i',str(native),'-i',str(audio_source),
                            '-map','0:v:0','-map','1:a:0','-c:v','copy','-af','apad',
                            '-t',str(native_media['duration_seconds']),'-c:a','aac','-movflags','+faststart',str(native_view)],
                           capture_output=True,check=True)
            write(view_receipt,json.dumps({'inputs':view_inputs,'sha256':sha(native_view),
                        'video_policy':'Original encoded video stream copied; no video edits.',
                        'audio_policy':'Common Serena WAV added; silence padded only beyond its duration.'},indent=2)+'\n')
        verify(native_view,frames=native_media['frames'])
        sheet(video,folder,[0,16,32,48,64,100,136,152,168,184,200])
        boundaries={}
        if key in speech:
            boundaries={'speech_start':speech[key]['narration_starts_seconds'],
                        'speech_end':speech[key]['narration_ends_seconds']}
            audio_file=ROOT/'inputs'/key/'audio.wav'
            if audio_file.exists():
                raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(audio_file),'-ac','1','-ar','24000','-f','f32le','-'])
                wav=np.frombuffer(raw,dtype=np.float32);hop=240
                rms=np.array([np.sqrt(np.mean(wav[i:i+hop]**2)) for i in range(0,len(wav),hop)])
                active=np.flatnonzero(rms>max(float(rms.max())*.025,.0001))
                if len(active):boundaries={'speech_start':active[0]*.01,'speech_end':(active[-1]+1)*.01}
            for name,t in boundaries.items():
                center=round(t*25);idx=[max(0,min(200,center+d)) for d in (-2,-1,0,1,2)]
                sheet(video,folder,idx,name+'.jpg',crop=(.10,.015,.56,.32))
        n=native_media['frames']
        tail_indices=[184,200,n-21,n-11,n-1] if n>201 else list(range(max(0,n-5),n))
        sheet(native,folder,tail_indices,name='native_tail.jpg')
        continuation_boundaries=[]
        # Official concatenation appends frames after the retained context:
        # LongCat: 93 + 80 + 80; InfiniteTalk: 81 + 72 + remainder.
        for boundary in {'longcat':[93,173], 'infinitetalk':[81,153]}.get(engine,[]):
            filename=f'continuation_{boundary}.jpg'
            sheet(video,folder,list(range(boundary-3,boundary+4)),name=filename)
            continuation_boundaries.append({'frame':boundary,'seconds':boundary/25,
                                           'sheet':str((folder/filename).relative_to(ROOT))})
        poster=folder/'poster.jpg'
        if not poster.exists():
            subprocess.run(['ffmpeg','-v','error','-y','-ss','4','-i',str(video),'-frames:v','1',str(poster)],capture_output=True,check=True)
        seconds=m['render_seconds']
        ltx_seconds=None
        if engine=='latentsync' and (baseline.parent/'metrics.json').exists():
            ltx_seconds=json.loads((baseline.parent/'metrics.json').read_text())['generation_including_model_loading_seconds']
        row={'video':str(video.relative_to(ROOT)),'native':str(native_view.relative_to(ROOT)),
             'native_original':str(native.relative_to(ROOT)),
             'video_sha256':media['sha256'],
             'native_tail':str((folder/'native_tail.jpg').relative_to(ROOT)),
             'poster':str(poster.relative_to(ROOT)),'action_frames':str((folder/'action_frames.jpg').relative_to(ROOT)),
             'seconds':seconds,'ltx_seconds':ltx_seconds,'native_duration':native_media['duration_seconds'],
             'findings':findings.get(engine+'/'+key),'boundaries':boundaries,'size':media['size'],
             'hold_seconds':m.get('final_frame_hold_seconds',0),
             'continuation_boundaries':continuation_boundaries}
        if engine=='latentsync':
            row['source_motion']=str(baseline.relative_to(ROOT))
            if natural:row['ltx_motion_reused']=True
        if (folder/'handover_detail.jpg').exists():
            row['handover_detail']=str((folder/'handover_detail.jpg').relative_to(ROOT))
        product['routes'][engine]=row;measurements.append(m)
        pcm_by_engine[engine]=subprocess.check_output(['ffmpeg','-v','error','-i',str(video),'-vn','-ac','1','-ar','24000','-f','s16le','-'])
    if pcm_by_engine:
        first=next(iter(pcm_by_engine.values()))
        identical=all(pcm==first for pcm in pcm_by_engine.values())
        assert identical,f'Different candidate narration: {key}'
        audio_checks.append({'product':key,'engines':list(pcm_by_engine),'decoded_pcm_equal':identical,
                             'pcm_sha256':hashlib.sha256(first).hexdigest()})
    data['products'].append(product)
for engine,title in ENGINES:
    videos=[ROOT/'results'/engine/key/'video.mp4' for key,label in CASES]
    if not all(p.exists() for p in videos):continue
    out=ROOT/'results'/engine/'three_products.mp4';manifest=out.with_suffix('.inputs.json')
    hashes=[sha(p) for p in videos]
    if not out.exists() or not manifest.exists() or json.loads(manifest.read_text())!=hashes:
        command=['ffmpeg','-v','error','-y']
        for movie in videos:command.extend(['-i',str(movie)])
        parts=[]
        for i in range(3):
            parts.extend([f'[{i}:v]trim=duration=8.04,setpts=PTS-STARTPTS[v{i}]',
                          f'[{i}:a]atrim=duration=8.04,asetpts=PTS-STARTPTS[a{i}]'])
        parts.append(''.join(f'[v{i}][a{i}]' for i in range(3))+'concat=n=3:v=1:a=1[v][a]')
        command.extend(['-filter_complex',';'.join(parts),'-map','[v]','-map','[a]',
                        '-r','25','-t','24.12','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac',str(out)])
        subprocess.run(command,capture_output=True,check=True)
        manifest.write_text(json.dumps(hashes,indent=2)+'\n')
    verify(out,frames=603)
    next(r for r in data['routes'] if r['key']==engine)['compilation']=str(out.relative_to(ROOT))
write(ROOT/'verification.json',json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
write(ROOT/'audio_verification.json',json.dumps(audio_checks,ensure_ascii=False,indent=2)+'\n')
write(ROOT/'measured_results.json',json.dumps(measurements,ensure_ascii=False,indent=2)+'\n')
write(ROOT/'review_data.json',json.dumps(data,ensure_ascii=False,indent=2)+'\n')
summary=['# 女装交接实测结果', '',
         f'实际推理完成：{len(measurements)}/9 条。生成完成与动作验收分开记录。', '',
         '统一成片：576×768，3:4，25 FPS，每件 8.04 秒。三件合辑为 24.12 秒顺序剪辑。', '',
         '耗时仅代表本次 DGX Spark 与兼容依赖环境；单件推理时间不包含各路线共享模型加载。LTX 动作耗时另列，包含其模型加载。', '',
         '| 商品 | 路线 | 单件推理 | LTX 动作 | 原生时长 |',
         '| --- | --- | --- | --- | --- |']
for product in data['products']:
    for engine,title in ENGINES:
        row=product['routes'].get(engine)
        if row:
            motion=f"{row['ltx_seconds']/60:.1f} 分钟" if row['ltx_seconds'] else '—'
            summary.append(f"| {product['label']} | {title} | {row['seconds']/60:.1f} 分钟 | {motion} | {row['native_duration']:.2f} 秒 |")
        else:
            summary.append(f"| {product['label']} | {title} | 等待完成 | — | — |")
summary.extend(['', '## 逐件观察', ''])
for product in data['products']:
    summary.extend([f"### {product['label']}", ''])
    for engine,title in ENGINES:
        row=product['routes'].get(engine)
        finding=row.get('findings') if row else None
        summary.append(f"- **{title}**：{finding or ('已生成，视觉检查待完成。' if row else '等待生成。')}")
    summary.append('')
summary.extend(['## 判断范围', '',
                '观察来自实际动作、语音边界、续接位置和原生末段帧。未据抽样宣称全帧手指、布料接触或所有音节精确同步。', '',
                'LTX 有六个动作关键帧；LatentSync 保留其完整身体动作。InfiniteTalk 只使用默认稀疏参考，LongCat 只使用首帧与动作提示。结果反映本次各路线配置，不能当作相同动作约束下的模型排名。', '',
                '[打开对比页](review.html) · [完整媒体核验](verification.json) · [同源音轨核验](audio_verification.json) · [图像提示记录](assets/image_prompts.json)', ''])
if natural:
    summary.extend(['## 本轮配音', '', '采用已选第一版「日常女声」Serena 默认语气，直接使用试听页三件商品的短句 WAV，保持采样内容、语速、音高和响度。只增加开口前与收口后的静音。', '',
                    '复用上一轮 LTX 动作素材；LatentSync、LongCat 与 InfiniteTalk 均以新音频重新推理。沿用相同图片、动作提示和种子。LTX 动作耗时为上一轮记录，没有计入本轮新生成。', ''])
write(ROOT/'results_summary.md','\n'.join(summary))
template=Path(__file__).with_name('review_template.html').read_text()
if natural:
    template=template.replace('三件女装 · 三条数字人路线','三件女装 · 日常女声合成')
    template=template.replace('<h1>三件女装，三条数字人路线</h1>','<h1>三件女装 · 日常女声合成</h1>')
    template=template.replace('统一柔和女声 · Serena','已选第一版 · Serena 日常女声')
    template=template.replace('每件独立生成 8.04 秒；','新配音重新驱动三条路线，LTX 动作复用上一轮素材。每件成片 8.04 秒；')
    template=template.replace('natural_voice_v2/index.html','../natural_voice_v2/index.html').replace('marketing_voice_v1/index.html','../marketing_voice_v1/index.html')
    template=template.replace('；另含 LTX 动作 ${(row.ltx_seconds/60).toFixed(1)} 分钟','；${row.ltx_motion_reused?"复用原 LTX 动作":"另含 LTX 动作 "+(row.ltx_seconds/60).toFixed(1)+" 分钟"}')
elif (ROOT/'natural_synthesis_v2/review.html').exists():
    template=template.replace('<div class="links"><a href="natural_voice_v2/index.html">',
                              '<div class="links"><a href="natural_synthesis_v2/review.html">已选日常女声 · 新合成视频</a><a href="natural_voice_v2/index.html">')
write(ROOT/'review.html',template)
print(json.dumps({'verified_candidates':len(measurements),'verified_media':len(verification),'format':'3:4'}),flush=True)
