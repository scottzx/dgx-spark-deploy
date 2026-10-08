#!/usr/bin/env python3
"""Local review shows all variants and quality decisions independently of technical PASS."""
import html,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
m=json.loads((ROOT/'manifest.json').read_text());q=json.loads((ROOT/'quality_review.json').read_text()) if (ROOT/'quality_review.json').exists() else {'clips':[]}
review={x['id']:x for x in q['clips']};method={'msr':'A · MSR 参考图','msr_first':'B · MSR＋首帧','msr_first_last':'C · MSR＋首尾帧'}
quality_labels={'pass_at_samples':'采样检查通过','partial_at_samples':'部分满足，仍有缺陷','fail_at_samples':'动作或状态失败'}
e=html.escape
parts=['''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>木马计 · V2 控制实验</title><style>body{margin:0;background:#171815;color:#ebe8dc;font:16px/1.55 system-ui}main{max-width:1500px;margin:auto;padding:30px}h1{font-size:36px;margin:0}h2{border-top:1px solid #444;padding-top:24px}h3{margin:8px 0}a{color:#d5b56c}video,img{width:100%;display:block;background:#111}video{aspect-ratio:16/9}.lead{color:#c4c4b3;max-width:1100px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{background:#252721;padding:12px;border-radius:8px}small{color:#b1b39d}.frames{display:grid;grid-template-columns:1fr 1fr;gap:12px}summary{cursor:pointer;padding:8px 0}.tag{color:#d5b56c;font-weight:600}.pass{color:#92ce91}.partial{color:#e8c77e}.fail{color:#ee8e86}.sync{padding:10px 20px;background:#cfb16d;border:0;border-radius:6px;font-size:16px;cursor:pointer}@media(max-width:950px){.grid{grid-template-columns:1fr}.frames{grid-template-columns:1fr}}</style><main><h1>木马计 · V2 控制实验</h1><p class="lead">四个镜头 × 三种控制方式 × 两个种子，共24个新视频。组内固定提示词、MSR参考图、权重、8步、5秒和分辨率。静态关键帧全部由本地 Qwen Image 2.1 BF16 40步生成；本页展示实际推理视频。旧版只作为历史参考。</p>''']
completed=sum((ROOT/'clips'/x['id']/'result.json').exists() for x in m['shots']);parts.append(f'<p class="tag">已生成 {completed}/24 · native768×448 → delivery768×432 · 24fps</p>')
parts.append(f'<p>完整镜头严格通过 {q.get("strict_full_clip_accepted",0)}/24。首尾帧改善了部分动作结尾；下梯开头方向、门闩机械结构、后排持续交战仍未全部解决。</p>')
if (ROOT/'action_excerpt.mp4').exists():parts.append('<h2>动作节选 · 8秒</h2><p>下梯2秒 → 夺门交锋3秒 → 军团交战3秒。按人工检查的时间区间剪辑；战斗背景仍有站立和空挥，音轨未做听审，完整镜头仍待返修。</p><video id="action-excerpt" controls preload="metadata" src="action_excerpt.mp4"></video>')
if (ROOT/'comparison_40s.mp4').exists():parts.append('<h2>A/B/C 同种子对比 · 40秒</h2><p>从左到右为MSR、首帧、首尾帧；每个镜头依次显示两个种子。比较视频无声。</p><video style="aspect-ratio:1728/372" controls preload="metadata" src="comparison_40s.mp4"></video>')
if (ROOT/'selected_diagnostic.mp4').exists():parts.append('<details><summary>四镜头诊断样片 · 20秒（包含失败动作）</summary><p>逐镜挑选的较好候选，保留完整5秒用于检查缺陷；S16门闩结构错误，不能投入正式成片。</p><video controls preload="metadata" src="selected_diagnostic.mp4"></video></details>')
parts.append('<p><a href="qa.md">验收记录</a> · <a href="shot_specs.json">镜头状态规格</a> · <a href="manifest.json">冻结输入清单</a> · <a href="../video_msr_v1/review.html">旧版100秒影片</a></p>')
for case in m['cases']:
 cid=case['id'];parts.append(f'<section data-case="{cid}"><h2>{cid} · {e(case["title"])}</h2>')
 parts.append('<details><summary>查看已选择的起止关键帧与动作条件</summary><div class="frames">')
 for phase in ('start','end'):parts.append(f'<figure><img loading="lazy" src="{case["keyframes"][phase]["file"]}"><figcaption>{"起始" if phase=="start" else "结束"}状态 · Qwen Image2.1</figcaption></figure>')
 parts.append('</div><p>'+e('；'.join(case['spec']['acceptance']))+'</p></details>')
 for seed in (2026100601,2026100602):
  parts.append(f'<h3>种子 {seed}</h3><button class="sync" onclick="sync(this)">同时从头播放这一组</button><div class="grid">')
  for meth in method:
   job=next(x for x in m['shots'] if x['case_id']==cid and x['seed']==seed and x['method']==meth);jid=job['id'];status=review.get(jid,{});label=status.get('quality_status','待人工验收');notes=status.get('notes','技术成功不代表动作合格。')
   parts.append(f'<article class="card"><h3>{method[meth]}</h3><p class="{e(label.split("_")[0])}">{e(quality_labels.get(label,label))}</p>')
   if (ROOT/'clips'/jid/'delivered.mp4').exists():parts.append(f'<video controls preload="metadata" poster="inspection/{jid}/f001.jpg" src="clips/{jid}/delivered.mp4"></video>')
   else:parts.append('<p>等待推理</p>')
   parts.append(f'<p>{e(notes)}</p><small>{e(jid)}</small><details><summary>11个时间采样</summary><img loading="lazy" src="inspection/{jid}_contact.jpg"></details></article>')
  parts.append('</div>')
 parts.append('</section>')
parts.append('''<p class="lead">人工评价依据每段11个采样帧（每0.5秒＋末帧）；不等同于逐帧动作和音轨终验。首尾约束绑定原生第0/120帧，交付视频为前120帧。严格通过与较好候选分别记录。</p></main><script>function sync(b){let vids=b.nextElementSibling.querySelectorAll('video');vids.forEach(v=>{v.pause();v.currentTime=0;v.muted=true;v.play().catch(()=>{})})}</script></html>''')
(ROOT/'review.html').write_text('\n'.join(parts));print(completed)
