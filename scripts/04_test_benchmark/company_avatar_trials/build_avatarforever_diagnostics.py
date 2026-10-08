"""Build three default-cache trials and one mouth diagnostic outside the primary 21."""
import hashlib
import html
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]/'docs/benchmarks/14_company_avatar_comparison'
PRODUCTS = [('original','原味',4.34),('diet','健怡',5.16),('zero','零度',5.49)]
VARIANTS = [(engine,title,cache,product) for product,_,_ in PRODUCTS for engine,title,cache in [
    ('avatarforever', '主测试：商品提示词＋开启历史特征缓存', True),
    ('avatarforever_nocache', '默认缓存配置：相同商品提示词＋关闭历史特征缓存', False),
]] + [('avatarforever_speaking','仅口播诊断：作者提示词＋关闭历史特征缓存',False,'original')]
for engine, _, _, product in VARIANTS:
    folder = ROOT/'results'/engine/product
    if not (folder/'video.mp4').exists() or not (folder/'metrics.json').exists():
        raise SystemExit(f'Diagnostic video is not yet available: {engine}')

verification = []
cards = []
for engine, title, cache, product in VARIANTS:
    folder = ROOT/'results'/engine/product
    baseline_receipt = json.loads((ROOT/'results/avatarforever'/product/'metrics.json').read_text())
    video = folder/'video.mp4'
    receipt = json.loads((folder/'metrics.json').read_text())
    if receipt['input_sha256'] != baseline_receipt['input_sha256']:
        raise RuntimeError('Diagnostic input hashes differ from the primary case')
    if engine != 'avatarforever' and receipt['ar_history_feature_cache'] != cache:
        raise RuntimeError('Receipt cache setting differs from diagnostic definition')
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    if digest != receipt['video_sha256']:
        raise RuntimeError('Diagnostic video differs from the actual Spark receipt')
    streams = json.loads(subprocess.check_output([
        'ffprobe','-v','error','-count_frames','-show_streams','-of','json',str(video)]))['streams']
    media = next(s for s in streams if s['codec_type']=='video')
    if (int(media['nb_read_frames']), media['width'], media['height']) != (201,768,512):
        raise RuntimeError('Diagnostic frame count or dimensions differ from the test')
    if abs(float(media['duration'])-8.04)>.01 or not any(s['codec_type']=='audio' for s in streams):
        raise RuntimeError('Diagnostic duration or audio differs from the test')
    subprocess.run(['ffmpeg','-v','error','-i',str(video),'-f','null','-'],check=True,capture_output=True)
    verification.append({'engine':engine,'product':product,'path':str(video.relative_to(ROOT)),
                         'sha256':digest,'full_decode':True,'frames':201,'duration':8.04,
                         'input_sha256':receipt['input_sha256'],'cache':cache,
                         'product_action_requested':engine!='avatarforever_speaking'})
    sheets = []
    for phase, label in [('opening','开口'),('ending','收口')]:
        sheet = folder/f'{phase}_consecutive_faces.jpg'
        if sheet.exists():
            sheets.append(f'<figure><figcaption>{label}五个连续帧，上方 LTX 基线，下方该对照</figcaption><img src="{sheet.relative_to(ROOT)}"></figure>')
    active = folder/'active_speech_faces.jpg'
    if not active.exists() or active.stat().st_mtime < video.stat().st_mtime:
        graph = 'select=between(n\\,64\\,116)*not(mod(n-64\\,4)),crop=128:128:320:80,scale=256:256:flags=bilinear,tile=7x2:padding=4'
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(video),'-vf',graph,'-frames:v','1',str(active)],check=True)
    sheets.append(f'<figure><figcaption>说话段抽样：2.56–4.64 秒，每隔 0.16 秒一帧；仅该对照的实际画面</figcaption><img src="{active.relative_to(ROOT)}"></figure>')
    seconds = receipt['render_seconds']
    prompt = receipt.get('prompt')
    prompt_detail = f'<details><summary>实际提示词</summary><pre>{html.escape(prompt)}</pre></details>' if prompt else ''
    action_frames = ''.join(f'<figure><figcaption>{t:g} 秒，上方 LTX，下方该对照</figcaption><img src="results/{engine}/{product}/phase_{t:g}.jpg"></figure>'
                            for t in [.8,1.6,2.4,4,5.6,8] if (folder/f'phase_{t:g}.jpg').exists())
    action_note = '只检查口播，不要求拿放商品。' if engine=='avatarforever_speaking' else '沿用相同商品动作提示词。'
    cards.append((product,f'''<article class="case"><h2>{title}</h2><p>{action_note} 本组生成 {seconds:.1f} 秒。</p>
<video controls playsinline preload="metadata" src="results/{engine}/{product}/video.mp4"></video>
<p><a href="results/{engine}/{product}/metrics.json">原始实测记录</a></p>{prompt_detail}
<details><summary>说话边界与说话段实际帧</summary>{''.join(sheets)}</details><details><summary>动作关键帧</summary>{action_frames}</details></article>'''))

qa = json.loads((ROOT/'quality_review.json').read_text()).get('observations',[])
findings = [r for r in qa if r.get('engine_key') in {'avatarforever_nocache','avatarforever_speaking'}]
notes = ''.join(f'<p>{html.escape(r["engine"])}：{html.escape(r["finding"])}</p>' for r in findings)
groups=[]
for product,label,end in PRODUCTS:
    body=''.join(card for p,card in cards if p==product)
    grid='grid' if product=='original' else 'grid pair'
    groups.append(f'<section class="comparison"><h2>{label} · 同一配音 · 8.04 秒</h2><p><button data-time="0">同步从头播放</button><button data-time="1.9">比较开口</button><button data-time="{end}">比较收口</button><button data-stop>暂停</button></p><div class="{grid}">{body}</div></section>')
page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Avatar-Forever 三组缓存与口播对照</title><style>body{margin:0;background:#f7f4ee;color:#24211f;font:16px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1200px;margin:auto;padding:24px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.pair{grid-template-columns:repeat(2,1fr)}article{background:white;padding:16px;border-radius:10px}h2{font-size:19px}video,img{width:100%}button{padding:8px 12px;margin:4px}a{color:#a7212b}pre{white-space:pre-wrap;font:14px/1.6 sans-serif}figure{margin:12px 0}figcaption{font-size:13px}@media(max-width:800px){.grid{grid-template-columns:1fr}}</style>
<main><p><a href="review.html">返回七种模型、三组商品主测试</a></p><h1>Avatar-Forever：默认缓存配置与口播补充对照</h1>
<p>每组对照使用相同首帧、Serena 音频、随机种子和尺寸。官方脚本默认关闭历史特征缓存，三条补充商品视频采用这个设置，其余商品条件与主测试一致。另外一条原味诊断改为作者默认口播提示词，没有商品动作要求。</p>
<p>四条补充视频独立于 21 条主测试。对照一只改变历史特征缓存；原味对照二与对照一比较，只改变提示词。不能将同时改变两个条件的差异归因于其中一个条件。</p>
CARDS NOTES<p><a href="avatarforever_diagnostics_verification.json">完整解码及输入校验</a> · <a href="audio_verification.json">Serena 音轨一致性</a> · <a href="avatarforever_parameter_audit.json">官方参数核对</a></p></main>
<script>for(const section of document.querySelectorAll('.comparison')){const videos=[...section.querySelectorAll('video')];for(const button of section.querySelectorAll('button'))button.onclick=async()=>{document.querySelectorAll('video').forEach(v=>v.pause());if(button.hasAttribute('data-stop'))return;for(const [i,v] of videos.entries()){v.currentTime=Number(button.dataset.time);v.muted=i!==1;}await Promise.all(videos.map(v=>v.play()));};}</script></html>'''
(ROOT/'avatarforever_diagnostics.html').write_text(page.replace('CARDS',''.join(groups)).replace('NOTES',notes))
(ROOT/'avatarforever_diagnostics_verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
print('Avatar-Forever diagnostics: four extra clips fully decoded and input hashes verified')
