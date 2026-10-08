#!/usr/bin/env python3
"""Build a local video review page from actual generated clip receipts."""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def main():
    manifest = json.loads((ROOT/'manifest.json').read_text())
    review_file = ROOT/'inspection/manual_review.json'
    reviewed = {s['id']: s for s in json.loads(review_file.read_text())['shots']} if review_file.exists() else {}
    labels = {'pass_at_samples':'抽样较好','partial_at_samples':'部分符合','fail_at_samples':'关键偏差'}
    rows = []
    for shot in manifest['shots']:
        result = ROOT/'clips'/shot['id']/'result.json'
        if result.exists() and (result.parent/'delivered.mp4').exists():
            rows.append(dict(id=shot['id'],title=shot['title'],result=json.loads(result.read_text())))
    status = dict(completed=len(rows),total=20,film_available=(ROOT/'film.mp4').exists(),clips=rows)
    (ROOT/'local_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
    cards = []
    for shot in manifest['shots']:
        sid = shot['id']
        available = (ROOT/'clips'/sid/'delivered.mp4').exists()
        poster = f'inspection/{sid}_0.3.png' if (ROOT/'inspection'/(sid+'_0.3.png')).exists() else f'inputs/board_{sid}.png'
        visual = (f'<video controls preload="none" poster="{poster}"><source src="clips/{sid}/delivered.mp4" type="video/mp4"></video>' if available else f'<img src="inputs/board_{sid}.png" loading="lazy" alt="{sid} 分镜参考"><p class="muted pending">视频生成中 · 当前展示分镜图</p>')
        note = reviewed.get(sid)
        review = f'<p class="muted">画面抽样：{labels[note["status"]]} · <a href="qa.md">查看记录</a></p>' if note else ''
        cards.append(f'<article id="{sid}">{visual}<div class="body"><div class="row"><h2>{sid} · {html.escape(shot["title"])}</h2><span>{shot["start_s"]}–{shot["end_s"]} s</span></div><p class="muted">种子 {shot["seed"]} · {len(shot["slots"])} 张独立参考 · 5 秒</p>{review}<details><summary>动作与生成参数</summary><p>{html.escape(shot["motion"])}</p><p>{html.escape(shot["camera_sound"])}</p><a href="prompts/{sid}.txt">完整视频提示词</a> · <a href="inputs/board_{sid}.png">原分镜图</a></details></div></article>')
    film = ('<video id="film" controls preload="metadata" poster="inspection/S20_2.5.png"><source src="film.mp4" type="video/mp4"></video><p><a href="film.mp4" download>下载完整测试片</a> · <a href="result.json">成片技术验证</a></p>' if status['film_available'] else '<div class="waiting">完整测试片生成中</div>')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>木马计：夺门 · MSR V2 视频测试</title>
<style>:root{color-scheme:dark;--ink:#eee5d8;--muted:#b8ac9c;--line:#433a32;--accent:#e6b36d}*{box-sizing:border-box}body{margin:0;background:#171614;color:var(--ink);font:16px/1.7 system-ui,-apple-system,sans-serif}main,header,footer{max-width:1360px;margin:auto;padding:28px 32px}header{padding-top:40px}h1{font:600 clamp(28px,4vw,48px)/1.2 serif;margin:14px 0}h2{font-size:18px;margin:0}a{color:var(--accent);text-underline-offset:4px}.muted{color:var(--muted)}.eyebrow{font-size:12px;letter-spacing:.14em;color:var(--accent)}.tags{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}.tags span{border:1px solid var(--line);border-radius:30px;padding:5px 16px}video,img{display:block;width:100%;aspect-ratio:16/9;object-fit:contain;background:#090909}#film{max-height:72vh}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;margin-top:24px}article{border:1px solid var(--line);background:#201e1a;min-width:0}.body{padding:18px}.row{display:flex;justify-content:space-between;gap:14px;align-items:baseline}.row span{color:var(--accent);white-space:nowrap;font-size:13px}.body p,details{font-size:14px}.pending{margin:0;padding:8px 18px}.waiting{height:280px;display:grid;place-items:center;background:#111;border:1px solid var(--line);color:var(--muted)}footer{font-size:13px;border-top:1px solid var(--line)}.nav{display:flex;gap:22px;flex-wrap:wrap}@media(max-width:800px){main,header,footer{padding:22px 16px}.grid{grid-template-columns:1fr}}</style>
<header><div class="eyebrow">TROY · LTX-2.5 + LICON MSR V2 · VIDEO TEST V1</div><h1>木马计：夺门</h1><p>西农劝诱 → 木马入城 → 伏兵出马 → 夺门战 → 阿伽门农接应 → 军团交锋</p><div class="tags"><span>20 镜 · 100 秒</span><span>768 × 432 · 24 fps</span><span>原生 8 步 · 每镜一个种子</span><span>无对白 / 无配乐目标</span><span>已同步 __COUNT__ / 20 镜</span></div><p class="muted">复用当前人物、场景与 20 张分镜作为多参考条件。各镜独立生成后按剧情硬切拼接，环境声由视频模型生成。这是单轮效果测试；技术检查通过不代表动作、身份和人数完全符合剧本。</p><nav class="nav"><a href="../storyboard_v2/review.html">剧本与分镜</a><a href="manifest.json">固定输入与参数</a><a href="qa.md">视频审阅记录</a><a href="javascript:location.reload()">刷新进度</a></nav></header>
<main>__FILM__<h2 style="margin-top:32px">逐镜视频</h2><div class="grid">__CARDS__</div></main><footer class="muted">仍保留原生 768 × 448、121 帧视频；交付各镜裁去上下各 8 像素，取 120 帧、5 秒，保留模型生成的环境音。没有新增云端生图。</footer></html>'''
    page = page.replace('__COUNT__',str(len(rows))).replace('__FILM__',film).replace('__CARDS__','\n'.join(cards))
    (ROOT/'review.html').write_text(page)
    print(json.dumps(dict(completed=len(rows),film_available=status['film_available'])))

if __name__=='__main__':
    main()
