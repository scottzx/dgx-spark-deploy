#!/usr/bin/env python3
"""Verify full-film metadata, real playback and old/new synchronization."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent
URL='http://127.0.0.1:59137/video_ltx_main_v3/review.html'
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1080},device_scale_factor=1)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    response=page.goto(URL,wait_until='domcontentloaded');assert response.status==200
    assert page.locator('article').count()==20
    media=page.evaluate('''async()=>await Promise.all([...document.querySelectorAll('video')].map(v=>new Promise((resolve,reject)=>{
 const done=()=>resolve({src:v.getAttribute('src'),duration:v.duration,width:v.videoWidth,height:v.videoHeight});
 if(v.readyState>=1)return done();const timer=setTimeout(()=>reject(new Error('metadata timeout '+v.src)),25000);
 v.addEventListener('loadedmetadata',()=>{clearTimeout(timer);done()},{once:true});v.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('video error '+v.src))},{once:true});v.load();})))''')
    assert len(media)==24
    for x in media:
        expected=31.75 if x['src']=='battle.mp4' else 91.25 if x['src']=='film.mp4' else 100 if x['src'].endswith('film.mp4') or x['src']=='film_uncut_100s.mp4' else 5
        assert abs(x['duration']-expected)<.08 and x['width']>0 and x['height']>0,x
    page.evaluate("const v=document.querySelector('#film');v.muted=true;v.play()")
    page.wait_for_function("document.querySelector('#film').currentTime>2")
    played=page.evaluate("const v=document.querySelector('#film');v.pause();v.currentTime")
    page.evaluate("document.querySelector('#film').currentTime=67")
    page.wait_for_function("Math.abs(document.querySelector('#film').currentTime-67)<.02 && document.querySelector('#film').readyState>=2")
    page.screenshot(path=str(ROOT/'preview.png'))
    page.locator('#compare').click()
    page.wait_for_function("[...document.querySelectorAll('#comparison video')].every(v=>!v.paused&&v.currentTime>.35)")
    sync=page.evaluate("[...document.querySelectorAll('#comparison video')].map(v=>({time:v.currentTime,muted:v.muted,paused:v.paused}))")
    assert max(x['time'] for x in sync)-min(x['time'] for x in sync)<.25
    assert not errors,errors
    row=dict(status='PASS',url=URL,cards=20,media=media,full_film_played_to_s=played,seeked_to_s=67,synced=sync,browser_errors=errors,screenshot='preview.png')
    (ROOT/'browser_verification.json').write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in row.items() if k!='media'}))
    browser.close()
