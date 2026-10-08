#!/usr/bin/env python3
"""Validate fresh clips, inspect sampled frames, assemble exact-length film and HTML."""
import hashlib,html,json,subprocess
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parent
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(name,d):(ROOT/name).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def media(p,frames):
    x=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(p)]))
    v=next(s for s in x['streams'] if s['codec_type']=='video');a=next(s for s in x['streams'] if s['codec_type']=='audio')
    assert int(v['nb_read_frames'])==frames and [v['width'],v['height']]==[672,384] and v['r_frame_rate']=='24/1',x
    assert a['sample_rate']=='32000' and a['channels']==2,x
    subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(p),'-f','null','-'],check=True,capture_output=True)
    return dict(path=p.name,frames=frames,duration_s=frames/24,fps=24,size=[672,384],channels=2,audio_sample_rate=32000,full_decode=True,sha256=sha(p),container_duration_s=float(x['format']['duration']))
def assemble(jobs,out):
    cmd=['ffmpeg','-y','-v','error','-filter_complex_threads','1'];parts=[]
    for i,j in enumerate(jobs):
        cmd+=['-threads','1','-i',str(ROOT/j['clip_path'])]
        frames=j.get('edit_frames',120);duration=frames/24
        parts.append(f'[{i}:v]trim=end_frame={frames},setpts=N/(24*TB)[v{i}];[{i}:a]atrim=end={duration},asetpts=PTS-STARTPTS,apad,atrim=end={duration}[a{i}]')
    seq=''.join(f'[v{i}][a{i}]' for i in range(len(jobs)))
    parts.append(seq+f'concat=n={len(jobs)}:v=1:a=1[v][a]')
    frame_count=sum(j.get('edit_frames',120) for j in jobs)
    cmd+=['-filter_complex',';'.join(parts),'-map','[v]','-map','[a]','-frames:v',str(frame_count),'-r','24','-c:v','libx264','-threads','4','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-ar','32000','-ac','2','-b:a','192k','-movflags','+faststart',str(out)]
    subprocess.run(cmd,check=True)
    return media(out,frame_count)
def main():
    m=json.loads((ROOT/'manifest.json').read_text());checks=[];cards=[]
    repair=json.loads((ROOT/'repairs/manifest.json').read_text())
    assert repair['base_manifest_fingerprint']==m['fingerprint']
    replacement={j['id']:j for j in repair['jobs']};jobs=[]
    for original in m['jobs']:
        sid=original['id'];use_repair=sid in replacement
        j=dict(replacement[sid] if use_repair else original)
        j['job_manifest_fingerprint']=repair['fingerprint'] if use_repair else m['fingerprint']
        j['input_root']='repairs' if use_repair else '.'
        j['clip_path']=('repairs/' if use_repair else '')+'clips/'+sid+'/delivered.mp4'
        jobs.append(j)
    counts={model:sum(j['model']==model for j in jobs) for model in ('ltx','h3')}
    assert counts=={'ltx':19,'h3':1}
    inspect=ROOT/'inspection';inspect.mkdir(exist_ok=True)
    for j in jobs:
        sid=j['id'];p=ROOT/j['clip_path'];d=p.parent;r=json.loads((d/'result.json').read_text())
        assert r['input_fingerprint']==j['input_fingerprint'] and r['manifest_fingerprint']==j['job_manifest_fingerprint']
        assert sha(p)==r['media']['sha256'] and sha(ROOT/j['input_root']/j['first_frame'])==j['first_frame_sha256']
        v=media(p,120);v.update(id=sid,model=j['model'],clip_path=j['clip_path'],input_fingerprint=j['input_fingerprint'],job_manifest_fingerprint=j['job_manifest_fingerprint']);checks.append(v)
        folder=inspect/sid;folder.mkdir(exist_ok=True)
        frames=list(range(0,120,6 if sid in ('S15','S19','S20') else 12))+[119]
        expression='+'.join(f'eq(n,{n})' for n in frames)
        subprocess.run(['ffmpeg','-y','-v','error','-i',str(p),'-vf',f'select={expression.replace(",", chr(92)+",")},scale=336:192','-vsync','0',str(folder/'f%03d.jpg')],check=True)
        images=sorted(folder.glob('f*.jpg'));assert len(images)==len(frames)
        canvas=Image.new('RGB',(3*340,((len(frames)+2)//3)*218),(18,20,17));draw=ImageDraw.Draw(canvas)
        for i,(file,n) in enumerate(zip(images,frames)):
            x=(i%3)*340;y=(i//3)*218;canvas.paste(Image.open(file),(x,y+24));draw.text((x+5,y+5),f'{sid} {j["model"].upper()} t={n/24:.3f}s',fill='white')
        canvas.save(inspect/(sid+'_contact.jpg'))
        v['sample_frames']=frames
        cards.append(f'<article id="{sid}"><h3>{sid} · {html.escape(j["title"])} <span>{j["model"].upper()}</span></h3><p>{j["start_s"]}–{j["end_s"]}秒 · 新生成 · 种子{j["seed"]}</p><video controls preload="metadata" playsinline src="{j["clip_path"]}" poster="inputs/{sid}.png"></video><details><summary>首帧、动作描述与时间采样</summary><img src="inputs/{sid}.png"><pre>{html.escape(j["prompt"])}</pre><img src="inspection/{sid}_contact.jpg"></details></article>')
        print(json.dumps({'status':'CHECKED','shot':sid,'completed':len(checks),'total':20}),flush=True)
    save('verification.json',dict(status='PASS',manifest_fingerprint=m['fingerprint'],clips=checks,completed=20,total=20))
    save('selection.json',dict(base_manifest_fingerprint=m['fingerprint'],repair_manifest_fingerprint=repair['fingerprint'],model_counts=counts,selected=checks,rejected=[{'id':sid,'clip_path':'clips/'+sid+'/delivered.mp4','model':'h3','reason':'premature hatch reveal; S07 also deploys the ladder before the intended reveal'} for sid in replacement]))
    full=assemble(jobs,ROOT/'film.mp4');excerpt=assemble(jobs[13:],ROOT/'battle_35s.mp4')
    save('assembly_verification.json',dict(status='PASS',manifest_fingerprint=m['fingerprint'],repair_manifest_fingerprint=repair['fingerprint'],film=full,battle_excerpt=excerpt,source_clips=[{'id':v['id'],'sha256':v['sha256'],'model':v['model']} for v in checks],model_counts=counts))
    text='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>木马计：夺门 · LTX主 H3辅</title><style>body{background:#151811;color:#eeeae0;font:17px/1.7 system-ui;margin:30px auto;padding:0 24px;max-width:1400px}h1{font-size:34px}p{color:#cbcdb8}a{color:#e6c77a}video,img{width:100%;display:block;background:#080908}video{max-height:75vh}section{margin:32px 0;border-top:1px solid #555d42;padding-top:24px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}article{padding:14px;border:1px solid #4b5140;border-radius:8px}h3{margin:0}span{color:#e6c77a}pre{font:13px/1.6 monospace;white-space:pre-wrap;overflow-wrap:anywhere}details{margin:12px 0}button{padding:10px 18px;background:#e6c77a;border:0;border-radius:5px;font-size:16px;cursor:pointer}.note{padding:18px;border-left:4px solid #e6c77a;background:#24291e}@media(max-width:800px){.grid{grid-template-columns:1fr}}</style><h1>木马计：夺门 · LTX主 H3辅</h1><p>20镜全部重新生成 · LTX 17镜 / H3 3镜 · 完整100秒 · 672×384 · 24fps。LTX沿用连续攻防测试的独立首帧路径；H3用于陈情、静场和军阵待命。保留原生环境音。</p><p class="note" id="quality-note">技术检查20/20通过。视觉采样审阅见下方与测试记录；音轨未独立听审。此片用于试看，技术通过不等于动作和剧情全部合格。</p><section><h2>完整影片 · 100秒</h2><video id="film" controls preload="metadata" playsinline src="film.mp4" poster="inputs/S01.png"></video><p><a href="film.mp4" download>下载完整影片</a> · <a href="qa.md">测试记录</a> · <a href="manifest.json">冻结参数与模型分工</a></p></section><section><h2>守军拦截至广场大战 · 35秒</h2><video controls preload="metadata" playsinline src="battle_35s.mp4" poster="inputs/S14.png"></video></section><section><h2>与上一版完整片同步比较</h2><p>左为本轮混合流程，右为上一版LTX MSR完整片。同步比较默认静音，可在完整影片播放器单独开启声音。</p><button id="compare">从头同步播放</button><div class="grid" id="comparison"><video muted controls preload="metadata" playsinline src="film.mp4"></video><video muted controls preload="metadata" playsinline src="../video_msr_v1/film.mp4"></video></div></section><section><h2>逐镜结果</h2><div class="grid">'''+''.join(cards)+'''</div></section><script>document.querySelector('#compare').onclick=async()=>{const vs=[...document.querySelectorAll('#comparison video')];vs.forEach(v=>{v.pause();v.currentTime=0;v.muted=true});await Promise.all(vs.map(v=>v.play()))};</script></html>'''
    text=text.replace('LTX 17镜 / H3 3镜','LTX 19镜 / H3 1镜').replace('H3用于陈情、静场和军阵待命。','H3用于军阵待命。陈情和静场的H3初版提前开舱，已由新生成LTX片段替换；共生成22条、选入20条。')
    text=text.replace('<a href="manifest.json">冻结参数与模型分工</a>','<a href="selection.json">实际选片与模型分工</a>')
    (ROOT/'review.html').write_text(text)
    save('run_status.json',dict(status='generated_and_assembled',manifest_fingerprint=m['fingerprint'],repair_manifest_fingerprint=repair['fingerprint'],generated_clips=22,selected_clips=20,technical_pass=20,model_counts=counts,film=full,battle_excerpt=excerpt,visual_review='pending',audio_reviewed=False))
    print(json.dumps({'status':'PASS','film':full,'battle_excerpt':excerpt}))
if __name__=='__main__':main()
