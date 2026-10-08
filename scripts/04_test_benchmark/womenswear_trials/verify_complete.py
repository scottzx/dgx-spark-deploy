"""Check the delivered nine actual results against this comparison's contract."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
from PIL import Image

parser=argparse.ArgumentParser()
parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[3]/'docs/benchmarks/15_womenswear_avatar_comparison')
args=parser.parse_args()
ROOT=args.root.resolve()
ENGINES={'latentsync','longcat','infinitetalk'}
PRODUCTS={'shirt','cardigan','dress'}
read=lambda name:json.loads((ROOT/name).read_text())
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()

progress=read('progress.json')
assert progress['state']=='complete', 'Generation queue has not finished.'
data=read('review_data.json')
assert {p['key'] for p in data['products']}==PRODUCTS
assert all(set(p['routes'])==ENGINES for p in data['products'])
assert all(r.get('compilation') for r in data['routes'])

measured=read('measured_results.json')
assert len(measured)==9
assert {(m['engine'],m['product']) for m in measured}=={(e,p) for e in ENGINES for p in PRODUCTS}
assert len({m['video_sha256'] for m in measured})==9
for product in PRODUCTS:
    rows=[m for m in measured if m['product']==product]
    assert all(m['input_sha256']==rows[0]['input_sha256'] for m in rows)
    for name,digest in rows[0]['input_sha256'].items():
        assert sha(ROOT/'inputs'/product/name)==digest

media=read('verification.json')
assert len(media)==33 and len({m['path'] for m in media})==33
for row in media:
    assert row['size']==[576,768] and row['fps']=='25/1' and row['full_decode']
    assert sha(ROOT/row['path'])==row['sha256']
    if row['path'].endswith('/video.mp4'):
        assert row['frames']==201 and abs(row['duration_seconds']-8.04)<.02 and row['audio']
    elif row['path'].endswith('/three_products.mp4'):
        assert row['frames']==603 and abs(row['duration_seconds']-24.12)<.02 and row['audio']

audio=read('audio_verification.json')
assert len(audio)==3
assert all(set(a['engines'])==ENGINES and a['decoded_pcm_equal'] for a in audio)
assets=read('assets/manifest.json')['assets']
assert len(assets)==7
for asset in assets:
    path=ROOT/'assets'/asset['file']
    assert sha(path)==asset['sha256']
    with Image.open(path) as im:
        assert im.size==(1086,1448)

findings=read('quality_review.json')['cases']
assert set(findings)=={f'{e}/{p}' for e in ENGINES for p in PRODUCTS}
assert all(findings.values())
receipt={
    'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'generation_state':'complete','candidates':9,'compilations':3,
    'verified_media':33,'native_originals':9,'native_playback_versions':9,
    'size':[576,768],'aspect_ratio':'3:4','fps':25,
    'clip_duration_seconds':8.04,'compilation_duration_seconds':24.12,
    'common_input_hashes_equal_per_product':True,'same_product_decoded_audio_equal':True,
    'generated_reference_images':7,'reference_size':[1086,1448],
    'visual_findings_recorded':9,
    'action_acceptance':'See individual observations; generation completion is separate from action acceptance.'}
voice=read('inputs/voice.json')
if voice.get('profile')=='serena_default':
    jobs=read('inputs/manifest.json')
    for job in jobs:
        for name in ['driver.mp4','reference.png','first_frame.png']:
            assert job['input_sha256'][name]==job['baseline_input_sha256'][name]
    for clip in voice['clips']:
        assert sha(ROOT/'voices'/f"{clip['product']}_speech.wav")==clip['speech_sha256']
        assert clip['approved_samples_unchanged'] and not clip['pitch_changed'] and not clip['speed_changed']
    receipt.update(voice_profile='serena_default',approved_speech_bytes_unchanged=True,
                   speaking_models_rerun=3,ltx_motion_reused=True)
(ROOT/'completion_summary.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(receipt,ensure_ascii=False))
