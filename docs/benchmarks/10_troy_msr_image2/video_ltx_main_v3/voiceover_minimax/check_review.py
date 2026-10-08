#!/usr/bin/env python3
"""Check audible playback, video seeking, captions and narration metadata in Chromium."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:59137/video_ltx_main_v3/voiceover_minimax/review.html'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1080})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    assert page.goto(URL, wait_until='domcontentloaded').status == 200
    page.wait_for_function("[...document.querySelectorAll('video,audio')].every(v=>v.readyState>=1)")
    media = page.evaluate("[...document.querySelectorAll('video,audio')].map(v=>({id:v.id,duration:v.duration,width:v.videoWidth,height:v.videoHeight}))")
    assert len(media) == 3
    for m in media:
        expected = 31.75 if m['id'] == 'battle' else 91.25
        assert abs(m['duration'] - expected) < .03, m
    page.locator('#play').click()
    page.wait_for_function("document.querySelector('#film').currentTime>2")
    playback = page.evaluate("(()=>{const v=document.querySelector('#film');return {time:v.currentTime,muted:v.muted,volume:v.volume,paused:v.paused,decoded_audio_bytes:v.webkitAudioDecodedByteCount}})()")
    assert not playback['muted'] and not playback['paused'] and playback['volume'] == 1
    assert playback['decoded_audio_bytes'] > 0
    page.evaluate("const v=document.querySelector('#film');v.pause();v.textTracks[0].mode='showing';v.currentTime=70.6")
    page.wait_for_function("(()=>{const v=document.querySelector('#film');return Math.abs(v.currentTime-70.6)<.02&&v.readyState>=2&&v.textTracks[0].activeCues?.length>0})()")
    caption = page.evaluate("document.querySelector('#film').textTracks[0].activeCues[0].text")
    assert '门闩' in caption, caption
    page.screenshot(path=str(ROOT / 'preview.png'))
    response = page.request.get(URL.replace('review.html', 'film_voiced.mp4'), headers={'Range': 'bytes=0-31'})
    assert response.status == 206 and len(response.body()) == 32
    assert not errors, errors
    row = dict(status='PASS', url=URL, media=media, audible_playback=playback,
               seeked_to_s=70.6, active_caption=caption, range_http_status=206,
               browser_errors=errors, screenshot='preview.png',
               scope='Browser audio decoding and playback check; not independent perceptual listening.')
    (ROOT / 'browser_verification.json').write_text(json.dumps(row, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(row, ensure_ascii=False))
    browser.close()
