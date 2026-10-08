#!/usr/bin/env python3
"""Check actual media playback and synchronized review on an owned local browser."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:59137/video_msr_v2/review.html'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1080}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    response = page.goto(URL, wait_until='domcontentloaded')
    assert response.status == 200
    assert page.locator('section[data-case]').count() == 4
    assert page.locator('.card').count() == 24
    assert page.locator('button.sync').count() == 8
    media = page.evaluate('''async () => {
      const videos = [...document.querySelectorAll('video')];
      return await Promise.all(videos.map(v => new Promise((resolve, reject) => {
        const done = () => resolve({src:v.getAttribute('src'), duration:v.duration, width:v.videoWidth, height:v.videoHeight});
        if (v.readyState >= 1) return done();
        const timeout = setTimeout(() => reject(new Error('metadata timeout: ' + v.src)), 20000);
        v.addEventListener('loadedmetadata', () => {clearTimeout(timeout); done()}, {once:true});
        v.addEventListener('error', () => {clearTimeout(timeout); reject(new Error('video error: ' + v.src))}, {once:true});
        v.load();
      })));
    }''')
    assert len(media) == 27
    for item in media:
        expected = 8 if item['src'] == 'action_excerpt.mp4' else 40 if item['src'] == 'comparison_40s.mp4' else 20 if item['src'] == 'selected_diagnostic.mp4' else 5
        assert abs(item['duration'] - expected) < 0.05, item
        assert item['width'] > 0 and item['height'] > 0
    page.locator('button.sync').first.click()
    page.wait_for_function("[...document.querySelector('button.sync').nextElementSibling.querySelectorAll('video')].every(v => !v.paused && v.currentTime > .35)")
    synced = page.evaluate("[...document.querySelector('button.sync').nextElementSibling.querySelectorAll('video')].map(v => ({time:v.currentTime,muted:v.muted,paused:v.paused}))")
    assert max(v['time'] for v in synced) - min(v['time'] for v in synced) < 0.25
    page.evaluate("document.querySelectorAll('video').forEach(v => v.pause())")
    page.evaluate("document.querySelector('#action-excerpt').muted=true; document.querySelector('#action-excerpt').play()")
    page.wait_for_function("document.querySelector('#action-excerpt').currentTime > 1")
    excerpt_time = page.evaluate("document.querySelector('#action-excerpt').pause(); document.querySelector('#action-excerpt').currentTime")
    page.evaluate('window.scrollTo(0,0)')
    page.screenshot(path=str(ROOT / 'preview_final.png'))
    assert not errors, errors
    result = dict(status='PASS', url=URL, cases=4, cards=24, sync_groups=8, media=media, synced=synced, excerpt_played_to_s=excerpt_time, browser_errors=errors, screenshot='preview_final.png')
    (ROOT / 'browser_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'media'}))
    browser.close()
