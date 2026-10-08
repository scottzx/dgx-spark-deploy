#!/usr/bin/env python3
"""Verify the local review loads, plays all clips, and fits desktop/mobile."""
import argparse
import json
from pathlib import Path
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[3]/'docs/benchmarks/12_coca_cola_handheld'
parser=argparse.ArgumentParser();parser.add_argument('--url',required=True);args=parser.parse_args()
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(args.url,wait_until='networkidle')
    page.wait_for_function('Array.from(document.querySelectorAll("video")).every(v=>Number.isFinite(v.duration))')
    videos=page.locator('video');assert videos.count()==4
    info=videos.evaluate_all('(vs)=>vs.map(v=>({source:v.getAttribute("src"),duration:v.duration,width:v.videoWidth,height:v.videoHeight}))')
    assert abs(info[0]['duration']-24.12)<.08
    assert all(abs(v['duration']-8.04)<.08 for v in info[1:])
    main=videos.nth(0);main.evaluate('v=>{v.muted=true;return v.play()}')
    page.wait_for_function('document.querySelector("video").currentTime>.5')
    main.evaluate('v=>v.pause()')
    audio_preview=None
    if page.locator('audio').count():
        assert 'Serena' in page.locator('main').inner_text()
        preview=page.locator('audio').nth(0)
        expected=json.loads((ROOT/'actions/inputs/voice.json').read_text())['voice_preview_duration_seconds']
        page.wait_for_function('Number.isFinite(document.querySelector("audio").duration)')
        audio_preview=preview.evaluate('a=>({source:a.getAttribute("src"),duration:a.duration})')
        assert abs(audio_preview['duration']-expected)<.05
        preview.evaluate('a=>{a.muted=true;return a.play()}')
        page.wait_for_function('document.querySelector("audio").currentTime>.2')
        preview.evaluate('a=>a.pause()')
    page.screenshot(path=str(ROOT/'actions/review_desktop.jpg'),full_page=True,type='jpeg',quality=90)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.screenshot(path=str(ROOT/'actions/review_mobile.jpg'),full_page=True,type='jpeg',quality=90)
    comparison=None
    if page.locator('a[href="actions/transition_review/review.html"]').count():
        page.set_viewport_size({'width':1440,'height':1000})
        page.goto(urljoin(args.url,'actions/transition_review/review.html'),wait_until='networkidle')
        page.wait_for_function('Array.from(document.querySelectorAll("video")).every(v=>Number.isFinite(v.duration))')
        assert page.locator('video').count()==6
        assert page.locator('video').evaluate_all('vs=>vs.every(v=>Math.abs(v.duration-8.04)<.08)')
        section=page.locator('section').nth(0)
        section.locator('button').nth(0).click()
        page.wait_for_function('Array.from(document.querySelector("section").querySelectorAll("video")).every(v=>!v.paused&&v.currentTime>1.9)')
        positions=section.locator('video').evaluate_all('vs=>vs.map(v=>v.currentTime)')
        assert abs(positions[0]-positions[1])<.12
        section.locator('button').nth(2).click()
        assert section.locator('video').evaluate_all('vs=>vs.every(v=>v.paused)')
        page.screenshot(path=str(ROOT/'actions/transition_review/desktop.jpg'),full_page=True,type='jpeg',quality=90)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        comparison={'six_clips_loaded':True,'synchronized_playback_passed':True,'mobile_no_horizontal_overflow':True}
    assert not errors,errors
    (ROOT/'actions/browser_verification.json').write_text(json.dumps({'url':args.url,'videos':info,'audio_preview':audio_preview,'playback_passed':True,'mobile_no_horizontal_overflow':True,'transition_comparison':comparison,'page_errors':errors},ensure_ascii=False,indent=2)+'\n')
    browser.close()
print('PASS: metadata, playback, desktop and mobile layout')
