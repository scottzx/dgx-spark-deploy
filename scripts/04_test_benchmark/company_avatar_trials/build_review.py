#!/usr/bin/env python3
"""Build a comparison only from real, completed files; pending rows contain no substitute videos."""
import hashlib
import html
import json
from pathlib import Path
import shutil
import subprocess

PROJECT = Path(__file__).resolve().parents[3]
ROOT = PROJECT / 'docs/benchmarks/14_company_avatar_comparison'
BASE = PROJECT / 'docs/benchmarks/12_coca_cola_handheld/actions'
MODELS = [
    ('joyhallo', '京东 · JoyHallo', '从同一人物裁切肖像，单独检查口播'),
    ('joyvasa', '京东 · JoyVASA', '音频驱动肖像，单独检查表情与口型'),
    ('infinitetalk', '美团 · InfiniteTalk', 'LTX 分段关键帧引导，重新生成动作与口型；FusionX 8 步'),
    ('longcat', '美团 · LongCat-Video-Avatar 1.5', '参考图＋提示词＋音频，生成连续动作'),
    ('liveportrait', '快手 · LivePortrait', 'LTX 身体动作＋已有 Serena 视频的面部驱动'),
    ('latentsync', '字节 · LatentSync 1.6', 'LTX 动作视频＋音频，重新匹配口型'),
    ('avatarforever', '字节参与 · Avatar-Forever', '参考图＋提示词＋音频，开启历史特征缓存'),
]
PRODUCTS = [('original', '原味'), ('diet', '健怡'), ('zero', '零度')]
SPEECH_END = {'original':4.689583333333333, 'diet':5.511083333333333, 'zero':5.839041666666667}
ROOT.mkdir(parents=True, exist_ok=True)
(ROOT/'baseline').mkdir(exist_ok=True)
verification = []
previous = {}
if (ROOT/'verification.json').exists():
    previous = {row['path']:row for row in json.loads((ROOT/'verification.json').read_text())}

def verify(path, frames=201, duration=8.04):
    key = str(path.relative_to(ROOT))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    cached = previous.get(key)
    if cached and cached['sha256'] == digest and cached.get('full_decode') and cached['frames'] == frames:
        verification.append(cached)
        return cached
    result = subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-of', 'json', str(path)], check=True, capture_output=True, text=True)
    streams = json.loads(result.stdout)['streams']
    video = next(s for s in streams if s['codec_type'] == 'video')
    audio = next((s for s in streams if s['codec_type'] == 'audio'), None)
    subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-f', 'null', '-'], check=True, capture_output=True)
    row = {'path': str(path.relative_to(ROOT)), 'frames': int(video['nb_read_frames']),
           'duration': float(video['duration']), 'size': [video['width'], video['height']],
           'fps': video['avg_frame_rate'], 'audio': audio is not None,
           'sha256': digest, 'full_decode': True}
    if row['frames'] != frames or abs(row['duration']-duration) > .06 or not row['audio']:
        raise RuntimeError(f'Media does not match the common test: {row}')
    verification.append(row)
    return row

def aggregate(videos, output):
    manifest = output.with_suffix('.inputs.json')
    hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in videos]
    if not output.exists() or not manifest.exists() or json.loads(manifest.read_text()) != hashes:
        args = ['ffmpeg','-v','error','-y']
        for video in videos: args.extend(['-i',str(video)])
        parts = []
        for i in range(3):
            parts.extend([f'[{i}:v]trim=duration=8.04,setpts=PTS-STARTPTS[v{i}]',
                          f'[{i}:a]atrim=duration=8.04,asetpts=PTS-STARTPTS[a{i}]'])
        parts.append(''.join(f'[v{i}][a{i}]' for i in range(3))+'concat=n=3:v=1:a=1[v][a]')
        args.extend(['-filter_complex',';'.join(parts),'-map','[v]','-map','[a]',
                     '-r','25','-t','24.12','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac',str(output)])
        subprocess.run(args,check=True)
        manifest.write_text(json.dumps(hashes,indent=2)+'\n')
    return verify(output,frames=603,duration=24.12)

for product, label in PRODUCTS:
    dest = ROOT/'baseline'/f'{product}.mp4'
    if not dest.exists(): shutil.copy2(BASE/'dubbed'/product/'dubbed.mp4', dest)
    verify(dest)
aggregate([ROOT/'baseline'/f'{p}.mp4' for p,_ in PRODUCTS],ROOT/'baseline/three_products.mp4')

cards = []
rows = []
measurements = []
quality = {}
if (ROOT/'quality_review.json').exists():
    quality = {r.get('engine_key'):r['finding'] for r in json.loads((ROOT/'quality_review.json').read_text()).get('observations', [])}
for engine, title, scope in MODELS:
    cases = []
    videos = []
    for product, label in PRODUCTS:
        folder = ROOT/'results'/engine/product
        video = folder/'video.mp4'
        metrics = folder/'metrics.json'
        if not video.exists() or not metrics.exists(): continue
        videos.append(video)
        media = verify(video)
        receipt = json.loads(metrics.read_text())
        measurements.append(receipt)
        if media['sha256'] != receipt['video_sha256']:
            raise RuntimeError(f'Output hash does not match the Spark run receipt: {video}')
        seconds = receipt.get('render_seconds', receipt.get('generation_seconds', receipt.get('total_seconds')))
        timing = f' · 本组生成 {seconds:.1f} 秒' if isinstance(seconds,(int,float)) else ''
        if isinstance(seconds,(int,float)) and seconds>=60:
            timing = f' · 本组生成 {seconds/60:.1f} 分钟（{seconds:.1f} 秒）'
        native_duration = receipt.get('native_duration_seconds')
        hold = receipt.get('final_frame_hold_seconds',0)
        if hold:
            timing += f' · 原生 {native_duration:.2f} 秒，真实末帧延长显示 {hold*1000:.0f} 毫秒'
        if isinstance(native_duration,(int,float)) and native_duration>8.05:
            timing += f' · 原生 {native_duration:.2f} 秒，统一取前 8.04 秒'
        ending_preview = max(0,SPEECH_END[product]-.35)
        poster = folder/'poster.jpg'
        if not poster.exists() or poster.stat().st_mtime < video.stat().st_mtime:
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '4', '-i', str(video), '-frames:v', '1', str(poster)], check=True)
        pairs = []
        for time in [0, .8, 1.6, 2.4, 4, 5.6, 6.4, 7.2, 8]:
            args = ['ffmpeg', '-v', 'error', '-y', '-ss', str(time), '-i', str(ROOT/'baseline'/f'{product}.mp4'),
                    '-ss', str(time), '-i', str(video), '-filter_complex',
                    '[0:v]scale=384:256:force_original_aspect_ratio=decrease,pad=384:256:(ow-iw)/2:(oh-ih)/2[a];'
                    '[1:v]scale=384:256:force_original_aspect_ratio=decrease,pad=384:256:(ow-iw)/2:(oh-ih)/2[b];[a][b]vstack',
                    '-frames:v', '1', str(folder/f'phase_{time:g}.jpg')]
            phase = folder/f'phase_{time:g}.jpg'
            if not phase.exists() or phase.stat().st_mtime < video.stat().st_mtime:
                subprocess.run(args, check=True)
            pairs.append(f'<figure style="margin:0"><figcaption>{time:g} 秒</figcaption><img loading="lazy" src="results/{engine}/{product}/phase_{time:g}.jpg" alt="{label} {time:g} 秒：上方 LTX，下方本轮"></figure>')
        face_sheets = []
        for phase, caption in [('opening', '开口'), ('ending', '收口')]:
            sheet = folder/f'{phase}_consecutive_faces.jpg'
            if sheet.exists():
                face_sheets.append(f'<figure><figcaption>{caption}前后五个连续帧，间隔 0.04 秒；上方基线，下方本轮</figcaption><img loading="lazy" style="width:100%" src="results/{engine}/{product}/{phase}_consecutive_faces.jpg" alt="{label} {caption}处连续帧"></figure>')
        face_detail = '<details><summary>说话起止处连续帧</summary>'+''.join(face_sheets)+'</details>' if face_sheets else ''
        chunk_sheet = folder/'chunk_boundary_64_faces.jpg'
        if chunk_sheet.exists():
            face_detail += f'<details><summary>第 64 帧分段边缘：2.44–2.68 秒实际连续画面</summary><img loading="lazy" style="width:100%" src="results/{engine}/{product}/chunk_boundary_64_faces.jpg" alt="{label} 分段边缘连续七帧"></details>'
        native_end = folder/'native_end_10s.jpg'
        if native_end.exists():
            face_detail += f'<details><summary>原生第 10 秒结尾，查看裁剪范围之外的动作</summary><img loading="lazy" style="width:100%;max-width:768px" src="results/{engine}/{product}/native_end_10s.jpg" alt="{label} 原生 10 秒结束帧"></details>'
        cases.append(f'''<section class="case"><h3>{label} · 同一配音 · 8.04 秒</h3><div class="pair"><div><p>LTX＋Serena 基线</p><video controls playsinline preload="metadata" src="baseline/{product}.mp4"></video></div><div><p>{html.escape(title)}</p><video controls playsinline preload="metadata" poster="results/{engine}/{product}/poster.jpg" src="results/{engine}/{product}/video.mp4"></video></div></div><p><button data-time="0">从头同步播放</button><button data-time="1.9">检查开口</button><button data-time="{ending_preview:.4f}">检查收口与放回</button><button data-stop>暂停</button></p><details><summary>动作帧对照：上方基线，下方本轮</summary><div class="phases">{''.join(pairs)}</div></details>{face_detail}<p class="muted">{media['size'][0]}×{media['size'][1]} · 完整解码通过{timing} · <a href="results/{engine}/{product}/metrics.json">实测记录</a></p></section>''')
    status = f'已生成 {len(cases)}/3 组' if cases else '准备中，尚无成片'
    compilation = ''
    if len(videos) == 3:
        aggregate(videos,ROOT/'results'/engine/'three_products.mp4')
        compilation = f'<p><a href="results/{engine}/three_products.mp4">播放本项目三组合辑</a> · <a href="baseline/three_products.mp4">LTX 三组基线</a><span class="muted">（三段顺序剪辑，24.12 秒）</span></p>'
    rows.append(f'<tr><td><a href="#{engine}">{html.escape(title)}</a></td><td data-status="{engine}">{status}</td><td>{html.escape(scope)}</td></tr>')
    observation = f'<p class="notice">画面检查：{html.escape(quality[engine])}</p>' if engine in quality else ''
    pending = f'<p class="muted" data-progress="{engine}">模型准备与运行中；完成后更新真实结果。</p>'
    body = ''.join(cases) if cases else pending
    cards.append(f'<article id="{engine}"><h2>{html.escape(title)}</h2><p>{html.escape(scope)}</p>{observation}{compilation}{body}</article>')

page = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>六项数字人项目 · 三组商品对比</title><style>*{box-sizing:border-box}body{margin:0;background:#f7f4ee;color:#24211f;font:16px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1250px;margin:auto;padding:30px}h1{font-size:32px}h2{font-size:24px}h3{font-size:18px}a{color:#a7212b}article{margin:36px 0;border-top:1px solid #d9d0c6;padding-top:20px}.case{background:#fff;border:1px solid #e5ded5;border-radius:12px;padding:20px;margin:18px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:18px}video{width:100%;background:#222;border-radius:8px}button{padding:8px 12px;margin:4px;background:#f7f4ee;border:1px solid #d3c7b9;border-radius:6px;cursor:pointer}.muted{color:#776e64;font-size:14px}.phases{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.phases img{width:100%}table{width:100%;border-collapse:collapse;background:#fff}td,th{padding:12px;text-align:left;border-bottom:1px solid #e5ded5}.notice{border-left:4px solid #a7212b;padding:10px 16px;background:white}@media(max-width:720px){main{padding:16px}h1{font-size:26px}.pair{grid-template-columns:1fr}.phases{grid-template-columns:repeat(2,1fr)}table{font-size:13px}td,th{padding:8px}}</style><main><p class="muted">DGX Spark / GB10 · 三组商品 · Serena 柔和女声</p><h1>六项数字人项目，沿用同一组商品测试</h1><p>原味、健怡、零度各 8.04 秒。目标：拿起 → 手持介绍 → 放回并松手；同时检查口型、开口收口的连续性和包装稳定性。</p><p class="notice">京东一项包含 JoyHallo、JoyVASA 两种模型，因此分别记录七种模型。肖像模型的结果单独评价口播；沿用 LTX 动作的路线会明确标注动作来源。生成结束不代表动作或包装验收通过。</p><p id="batch-progress" class="muted"></p><button id="load-new" hidden>有新成片，加载最新结果</button><table><thead><tr><th>项目</th><th>进度</th><th>本轮测试方式</th></tr></thead><tbody>ROWS</tbody></table>CARDS<p class="muted">视频可单独开启声音。同步比较只播放本轮音轨。所有动作参照均为已有 LTX 生成视频；本轮没有实拍输入。<a href="verification.json">完整解码验证</a> · <a href="audio_verification.json">配音一致性</a> · <a href="input_manifest.json">共同输入与哈希</a></p></main><script>for(const section of document.querySelectorAll('.case')){const videos=[...section.querySelectorAll('video')];for(const button of section.querySelectorAll('button'))button.onclick=async()=>{document.querySelectorAll('video').forEach(v=>v.pause());if(button.hasAttribute('data-stop'))return;for(const [i,v] of videos.entries()){v.currentTime=Number(button.dataset.time);v.muted=i===0;}await Promise.all(videos.map(v=>v.play()));};}const initial=INITIAL;
document.querySelector('#load-new').onclick=()=>location.reload();
async function updateProgress(){try{const p=await fetch('progress.json',{cache:'no-store'}).then(r=>r.json());
document.querySelector('#batch-progress').textContent=`已完成 ${p.completed_cases}/${p.total_cases} 组${p.supplemental_completed_cases?` · ${p.supplemental_completed_cases} 条补充对照`:''} · 更新于 ${new Date(p.updated_at_utc).toLocaleTimeString('zh-CN')}`;
for(const [model,s] of Object.entries(p.models)){const name={original:'原味',diet:'健怡',zero:'零度'}[['original','diet','zero'][s.completed]];
const match=/Loading|Downloading|shards|weights/i.test(s.last)?null:s.last.match(/(\d+)\/(\d+) \[\d/);
let text=`已生成 ${s.completed}/3 组`;
if(s.state==='queued')text+='，等待 GPU';
if(s.state==='running')text+=`，正在生成${name}`+(match?`（${s.current_chunk?`分段 ${s.current_chunk}/${s.total_chunks}，`:"当前分段 "}${match[1]}/${match[2]} 步${match[1]===match[2]?"，处理画面":""}）`:'');
if(s.state==='failed')text+='，兼容性问题处理中';
for(const el of document.querySelectorAll(`[data-status="${model}"],[data-progress="${model}"]`))el.textContent=text;
if(s.completed>(initial[model]||0))document.querySelector('#load-new').hidden=false;
}}catch(e){}}
updateProgress();setInterval(updateProgress,15000);
</script></html>'''
if (ROOT/'avatarforever_diagnostics.html').exists():
    page = page.replace('<p id="batch-progress"', '<p><a href="avatarforever_diagnostics.html">Avatar-Forever 三组默认缓存配置与作者口播提示词对照</a></p><p id="batch-progress"')
if len(measurements)==21:
    page = page.replace('<p id="batch-progress"', '<p class="notice">本轮建议：优先保留 LTX 商品动作，用 LatentSync 1.6 处理口型。LivePortrait 可作面部驱动备选，但依赖已有口播视频。整段重新生成的三种模型尚未在三组中稳定完成商品流程；肖像模型仅用于口播比较。</p><p id="batch-progress"')
(ROOT/'review.html').write_text(page.replace('ROWS', ''.join(rows)).replace('CARDS', ''.join(cards)).replace('INITIAL',json.dumps({key:sum(r['engine']==key for r in measurements) for key,_,_ in MODELS})))
(ROOT/'verification.json').write_text(json.dumps(verification, ensure_ascii=False, indent=2)+'\n')
(ROOT/'measured_results.json').write_text(json.dumps(measurements, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({'verified_media': len(verification), 'page': str(ROOT/'review.html')}, ensure_ascii=False))
