"""Publish and verify actual audio auditions under the existing review server."""
import hashlib
import html
import json
import argparse
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[3]/'docs/benchmarks/15_womenswear_avatar_comparison'
OUT=ROOT/'marketing_voice_v1'
PROFILES=[('vivian_guide','A · 热情专业导购','热情、亲切，强调商品名和搭配卖点。'),
          ('vivian_live','B · 强节奏直播','更有冲劲，强调节奏、语气起伏和互动感。'),
          ('serena_full','C · 成熟饱满导购','声音中低、圆润，强调饱满气息和自信推荐。'),
          ('baseline','对照 · 原柔和风格','沿用原 Serena 的柔和风格提示，用同一段新文案生成对照。')]
parser=argparse.ArgumentParser()
parser.add_argument('--set',dest='voice_set',choices=['marketing','natural'],default='marketing')
args=parser.parse_args()
natural=args.voice_set=='natural'
if natural:
    OUT=ROOT/'natural_voice_v2'
    PROFILES=[('serena_default','1 · 日常女声','Serena 默认语气，让模型按正常说话节奏处理文案。'),
              ('serena_chat','2 · 随口介绍','Serena 加一句简短的聊天语气提示。'),
              ('vivian_default','3 · 明亮女声','Vivian 默认语气，比较另一种女声音色。')]
records=[];cards=[];verification=[]
for key,label,description in PROFILES:
    p=OUT/key/'receipt.json'
    if not p.exists():
        continue
    receipt=json.loads(p.read_text());records.append(receipt)
    for clip in receipt['clips']:
        wav=p.parent/(clip['key']+'.wav')
        digest=hashlib.sha256(wav.read_bytes()).hexdigest();assert digest==clip['sha256']
        subprocess.run(['ffmpeg','-v','error','-i',str(wav),'-f','null','-'],capture_output=True,check=True)
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(wav)]))
        s=probe['streams'][0];assert s['codec_type']=='audio' and int(s['sample_rate'])==24000 and s['channels']==1
        assert abs(float(s['duration'])-clip['duration_seconds'])<.01
        level=subprocess.run(['ffmpeg','-hide_banner','-i',str(wav),'-af',
            'loudnorm=I=-23:TP=-3:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True,check=True)
        t=level.stderr;stats=json.loads(t[t.rfind('{'):t.rfind('}')+1]);assert float(stats['input_tp'])<=-2.8
        assert abs(float(stats['input_i'])+23)<.5,(key,clip['key'],stats)
        verification.append({'path':str(wav.relative_to(OUT)),'sha256':digest,'sample_rate':24000,
                             'channels':1,'duration_seconds':float(s['duration']),
                             'integrated_lufs':float(stats['input_i']),'true_peak_dbfs':float(stats['input_tp']),
                             'full_decode':True})
    audition=next(c for c in receipt['clips'] if c['key']=='audition')
    hashes={c['key']:c['sha256'][:12] for c in receipt['clips']}
    shorts=''.join(f'<p class="cliplabel">{label2}</p><audio controls preload="metadata" src="{key}/{name}.wav?v={hashes[name]}"></audio>'
                   for name,label2 in [('shirt','白色衬衫'),('cardigan','粉色开衫'),('dress','黑色连衣裙')])
    same_text=(f'<details><summary>用上一轮文案做同词比较</summary><audio controls preload="metadata" '
               f'src="{key}/audition_original_text.wav?v={hashes["audition_original_text"]}"></audio>'
               '<p class="small">文案与下方上一轮对照相同。</p></details>') if natural and not receipt.get('exclude_original_text_control',False) else ''
    cards.append(f'<article><h2>{html.escape(label)}</h2><p>{html.escape(description)}</p>'
                 f'<audio controls preload="metadata" aria-label="{html.escape(label)}完整试听" src="{key}/audition.wav?v={hashes["audition"]}"></audio>'
                 f'<p class="small">{audition["duration_seconds"]:.2f} 秒 · 统一约 −23 LUFS · 自然语速</p>'
                 f'<details><summary>三件商品短句</summary>{shorts}</details>{same_text}'
                 f'<div class="links"><a href="{key}/audition.wav" download>下载配音</a>'
                 f'<a href="{key}/receipt.json">音色提示与参数</a></div></article>')
assert len(records)==(3 if natural else 4) and len(verification)==(15 if natural else 16),'All candidate profiles are required.'
assert len({next(c for c in r['clips'] if c['key']=='audition')['text'] for r in records})==1
assert len({next(c for c in r['clips'] if c['key']=='audition')['sha256'] for r in records})==len(records)
text=next(c for c in records[0]['clips'] if c['key']=='audition')['text']
previous_comparison=None
if natural:
    source=ROOT/'marketing_voice_v1/serena_full/audition.wav'
    old=json.loads((source.parent/'receipt.json').read_text())
    old_clip=next(c for c in old['clips'] if c['key']=='audition')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==old_clip['sha256']
    assert all(next(c for c in r['clips'] if c['key']=='audition_original_text')['text']==old_clip['text'] for r in records)
    target=OUT/'previous_serena_full.wav';shutil.copy2(source,target)
    prior_verification=json.loads((ROOT/'marketing_voice_v1/verification.json').read_text())
    prior_row=next(v for v in prior_verification if v['path']=='serena_full/audition.wav')
    assert prior_row['sha256']==old_clip['sha256'] and prior_row['full_decode']
    verification.append(dict(prior_row,path='previous_serena_full.wav',copied_from='../marketing_voice_v1/serena_full/audition.wav'))
    previous_comparison={'source':'../marketing_voice_v1/serena_full/audition.wav','sha256':old_clip['sha256'],
                         'text':old_clip['text'],'speaker':old['speaker'],'instruction':old['instruction']}
    cards.append('<article><h2>对照 · 上一轮成熟带货</h2><p>同样是 Serena，沿用上一轮强调带货表现的提示。'
                 '与上面各版的「同词比较」试听使用同一段文案。</p>'
                 f'<audio controls preload="metadata" aria-label="上一轮成熟带货对照" src="previous_serena_full.wav?v={old_clip["sha256"][:12]}"></audio>'
                 '<p class="small">这一段来自上一轮实际生成的配音，保持相同的试听响度。</p></article>')
title='用日常说话的方式介绍衣服' if natural else '更有感染力、更饱满的带货配音'
intro=('口语化文案，三种女声表达。试听统一响度，保留自然语速和音高；播放新的一条时，其他音频会自动暂停。'
       if natural else '三种候选方向，使用同一段女装介绍。试听已统一响度，保留自然语速和音高；播放新的一条时，其他音频会自动暂停。')
footer=('1 和 2 使用 Serena，3 使用 Vivian，均由本地 Qwen3-TTS 1.7B CustomVoice 实际生成。'
        '1、3 未添加风格指令，2 仅使用一句聊天提示。<br>这里提供音频试听，视频配音和口型尚未替换。<br>'
        '<a href="../marketing_voice_v1/index.html">上一轮带货音色</a> · <a href="../review.html">三路视频对比</a> · '
        '<a href="verification.json">音频核验记录</a>' if natural else
        '上面的说明是各候选的目标风格，实际听感请以试听为准。A、B 使用 Vivian，C 与柔和对照使用 Serena，均由本地 Qwen3-TTS 1.7B CustomVoice 实际生成。<br>'
        '这里提供音频试听；原视频配音和口型尚未替换。选定后需要一起调整介绍时长并重做口型，避免声音与嘴形错位。<br>'
        '<a href="../natural_voice_v2/index.html">自然语气试听</a> · <a href="../review.html">返回三路视频对比</a> · <a href="verification.json">音频核验记录</a> · '
        '<a href="https://github.com/QwenLM/Qwen3-TTS">模型官方说明</a>')
if natural and (ROOT/'natural_synthesis_v2/review.html').exists():
    footer=footer.replace('这里提供音频试听，视频配音和口型尚未替换。',
                          '第一版已用于视频合成：<a href="../natural_synthesis_v2/review.html">查看新配音视频与进度</a>。本页保留音频试听。')
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>'''+html.escape(title)+''' · 配音试听</title><style>
*{box-sizing:border-box}body{margin:0;background:#efeee9;color:#252b24;font-family:system-ui,-apple-system,sans-serif}
main{max-width:1160px;margin:auto;padding:36px 24px}h1{font-size:30px;margin:8px 0 16px}p{line-height:1.75;color:#576052}
.eyebrow{font-size:12px;letter-spacing:2px;color:#72816a}.intro{max-width:820px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin:28px 0}
article{background:white;border:1px solid #d9ddd2;border-radius:13px;padding:22px}article:last-child{grid-column:1/-1;background:#e8eadd}
h2{font-size:18px;margin:0 0 12px}audio{width:100%;margin:8px 0}.small,.cliplabel{font-size:12px}.cliplabel{margin:14px 0 0}
details{margin-top:14px}summary{cursor:pointer;color:#46643e}.links{display:flex;gap:18px;margin-top:20px;font-size:13px}a{color:#2c654a}
.copy{padding:16px 20px;background:#e3e8dc;border-radius:9px;line-height:1.85}footer{font-size:13px;border-top:1px solid #d4d9cc;padding-top:18px;color:#62715d;line-height:1.8}
@media(max-width:850px){.grid{grid-template-columns:1fr}main{padding:26px 18px}article:last-child{grid-column:auto}}
</style><main><div class="eyebrow">WOMENSWEAR / VOICE AUDITION</div><h1>'''+html.escape(title)+'''</h1>
<p class="intro">'''+html.escape(intro)+'''</p>
<div class="copy">''' + html.escape(text)+'''</div><section class="grid">'''+''.join(cards)+'''</section>
<footer>'''+footer+'''</footer></main>
<script>document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>document.querySelectorAll('audio').forEach(b=>{if(b!==a)b.pause()})))</script></html>'''
(OUT/'index.html').write_text(page)
(OUT/'manifest.json').write_text(json.dumps({'profiles':records,'existing_videos_changed':False,
    'planned_voice_design_output':False,'previous_comparison':previous_comparison,
    'scope':'Natural timing preserved; old-text controls isolate copy from delivery.' if natural else 'Three candidate styles and same-text baseline. Natural timing preserved.'},ensure_ascii=False,indent=2)+'\n')
(OUT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'profiles':len(records),'candidate_styles':3,'verified_audio':len(verification)}))
