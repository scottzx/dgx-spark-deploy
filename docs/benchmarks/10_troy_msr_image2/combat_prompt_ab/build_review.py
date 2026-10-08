#!/usr/bin/env python3
"""Decode-check actual outputs, make timestamped samples, and build the local review."""
import hashlib,html,json,subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parent
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def inspect(m):
 rows=[]
 for j in m['jobs']:
  d=ROOT/'clips'/j['id'];done=d/'result.json';video=d/'delivered.mp4'
  if not done.exists():continue
  r=json.loads(done.read_text());assert r['input_fingerprint']==j['input_fingerprint'] and r['manifest_fingerprint']==m['fingerprint']
  actual=sha(video);assert actual==r['media']['sha256']
  data=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(video)]))
  v=next(s for s in data['streams'] if s['codec_type']=='video');a=next(s for s in data['streams'] if s['codec_type']=='audio')
  assert [v['width'],v['height']]==[672,384] and int(v['nb_read_frames'])==120 and v['r_frame_rate']=='24/1'
  assert a['channels']==2 and a['sample_rate']=='32000'
  subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(video),'-f','null','-'],check=True,capture_output=True)
  out=ROOT/'inspection'/j['id'];out.mkdir(parents=True,exist_ok=True)
  positions=[6*n for n in range(20)]+[119]
  select='+'.join(f'eq(n\\,{f})' for f in positions)
  if not (out/'f021.jpg').exists():
   subprocess.run(['ffmpeg','-y','-v','error','-i',str(video),'-vf',f"select='{select}'",'-fps_mode','vfr','-q:v','2',str(out/'f%03d.jpg')],check=True)
  tilew,tileh=512,293;sheet=Image.new('RGB',(tilew*3,34+(tileh+24)*7),'#151515');draw=ImageDraw.Draw(sheet)
  draw.text((8,8),j['id'],fill='white')
  for i,f in enumerate(positions):
   pic=Image.open(out/f'f{i+1:03d}.jpg').convert('RGB');pic=pic.resize((tilew,tileh),Image.Resampling.LANCZOS)
   x=(i%3)*tilew;y=34+(i//3)*(tileh+24);sheet.paste(pic,(x,y));draw.text((x+8,y+tileh+5),f'{f/24:.3f}s',fill='white')
  sheet.save(ROOT/'inspection'/(j['id']+'_contact.jpg'),quality=90)
  rows.append(dict(id=j['id'],sha256=actual,input_fingerprint=j['input_fingerprint'],frames=120,size=[672,384],fps=24,duration_s=5,full_decode=True,samples_frames=positions))
 save(ROOT/'verification.json',dict(status='PASS' if len(rows)==12 else 'IN_PROGRESS',clips=rows,completed=len(rows),total=12))
 return rows
def review(m,rows):
 e=html.escape;quality={}
 p=ROOT/'quality_review.json'
 if p.exists():quality={x['id']:x for x in json.loads(p.read_text())['clips']}
 labels={'ltx_old':'LTX · 原动作描述','ltx_new':'LTX · 连续攻防描述','h3_old':'H3 · 原动作描述','h3_new':'H3 · 连续攻防描述'}
 parts=['''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>夺门打斗 · 提示词与模型对照</title><style>body{margin:0;background:#151813;color:#e9e7dd;font:16px/1.6 system-ui}main{max-width:1560px;margin:auto;padding:30px}h1{margin:0;font-size:36px}h2{border-top:1px solid #49503e;padding-top:24px}h3{margin:4px 0}.lead{color:#bfc5af;max-width:1200px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.card{background:#252a20;padding:12px;border-radius:8px}video,img{width:100%;display:block;background:#111}video{aspect-ratio:7/4}a{color:#d9bf7a}button{background:#d9bf7a;border:0;border-radius:6px;padding:12px 22px;font-size:16px;cursor:pointer}.tag{color:#ddc786}.notes{font-size:14px}summary{cursor:pointer}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #46503d;padding:10px;text-align:left}@media(max-width:1050px){.grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:650px){.grid{grid-template-columns:1fr}main{padding:18px}}</style><main><h1>夺门打斗 · 提示词与模型对照</h1><p class="lead">同一张 Qwen Image 2.1 首帧，两个本地视频模型 × 两种前景动作描述 × 三个种子，共12段新视频。每段5秒、672×384、24fps。画面包含六人，重点比较前景两人的剑矛交锋；镜头、背景动作和音效描述在模型内保持一致。</p><p class="lead">H3：现有 W8A8／FastH3-VSA 加速配置、4次去噪更新，原生完整H3 VAE解码。LTX：BF16 dev＋蒸馏LoRA、8步，原生LTX VAE解码。双方均仅使用首帧；本轮模型比较限定于这些部署配置。</p>''']
 parts.append(f'<p class="tag">实际完成 {len(rows)}/12 · 技术验收与打斗评价分别记录</p>')
 if quality:
  summary=json.loads(p.read_text()).get('summary','')
  parts.append('<p>'+e(summary)+'</p>')
 for name,title in [('best_duel.mp4','本轮较好打斗候选 · 完整5秒'),('comparison_15s.mp4','四组并排 · 三个种子共15秒')]:
  if (ROOT/name).exists():parts.append(f'<h2>{title}</h2><video controls preload="metadata" src="{name}"></video>')
 parts.append('<p><a href="qa.md">实测结论</a> · <a href="manifest.json">冻结输入</a> · <a href="acceptance.json">共同评价标准</a> · <a href="../video_msr_v2/review.html">上一轮</a></p><details><summary>共享首帧与提示词</summary><img style="max-width:900px" src="inputs/first.png"><div class="grid">')
 for k in labels:parts.append(f'<article class="card"><h3>{labels[k]}</h3><p class="notes">{e(m["prompts"][k])}</p></article>')
 parts.append('</div></details>')
 for seed in (2026100601,2026100602,2026100603):
  parts.append(f'<section data-seed="{seed}"><h2>种子 {seed}</h2><button class="sync" onclick="sync(this)">同时从头播放四组</button><div class="grid">')
  for model,variant in [('ltx','old'),('ltx','new'),('h3','old'),('h3','new')]:
   j=next(x for x in m['jobs'] if x['seed']==seed and x['model']==model and x['variant']==variant);jid=j['id'];q=quality.get(jid)
   parts.append(f'<article class="card"><h3>{labels[model+"_"+variant]}</h3>')
   if (ROOT/'clips'/jid/'delivered.mp4').exists():parts.append(f'<video controls preload="metadata" poster="inspection/{jid}/f001.jpg" src="clips/{jid}/delivered.mp4"></video>')
   else:parts.append('<p>等待生成</p>')
   if q:parts.append('<p class="notes">'+e(q['notes'])+'</p>')
   parts.append(f'<details><summary>21个时间采样</summary><img loading="lazy" src="inspection/{jid}_contact.jpg"></details></article>')
  parts.append('</div></section>')
 parts.append('''<p class="lead">共享种子数值不代表两种架构使用相同噪声。模型内的原／新描述使用相同种子；跨模型比较不是完整BF16底模能力排名。音轨保留，视觉评价与听审分别记录。</p></main><script>function sync(b){const vs=b.nextElementSibling.querySelectorAll('video');vs.forEach(v=>{v.pause();v.currentTime=0;v.muted=true});Promise.all([...vs].map(v=>v.play().catch(()=>{})))}</script></html>''')
 (ROOT/'review.html').write_text('\n'.join(parts))
def main():
 m=json.loads((ROOT/'manifest.json').read_text());rows=inspect(m);review(m,rows);print(json.dumps(dict(completed=len(rows),total=12)))
if __name__=='__main__':main()
