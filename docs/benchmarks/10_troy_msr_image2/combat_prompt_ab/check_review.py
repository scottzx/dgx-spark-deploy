#!/usr/bin/env python3
"""Actual local playback check using an owned headless browser."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent
URL='http://127.0.0.1:59137/combat_prompt_ab/review.html'
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page(viewport={'width':1440,'height':1080},device_scale_factor=1)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 response=page.goto(URL,wait_until='domcontentloaded');assert response.status==200
 assert page.locator('section[data-seed]').count()==3
 assert page.locator('section .card').count()==12 and page.locator('button.sync').count()==3
 media=page.evaluate('''async()=>await Promise.all([...document.querySelectorAll('video')].map(v=>new Promise((resolve,reject)=>{
 const done=()=>resolve({src:v.getAttribute('src'),duration:v.duration,width:v.videoWidth,height:v.videoHeight});
 if(v.readyState>=1)return done();const timer=setTimeout(()=>reject(new Error('metadata timeout '+v.src)),20000);
 v.addEventListener('loadedmetadata',()=>{clearTimeout(timer);done()},{once:true});v.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('video error '+v.src))},{once:true});v.load();})))''')
 assert len(media)==14
 for x in media:
  expected=15 if x['src']=='comparison_15s.mp4' else 5
  assert abs(x['duration']-expected)<.05 and x['width']>0 and x['height']>0,x
 page.locator('button.sync').first.click()
 page.wait_for_function("[...document.querySelector('button.sync').nextElementSibling.querySelectorAll('video')].every(v=>!v.paused&&v.currentTime>.35)")
 sync=page.evaluate("[...document.querySelector('button.sync').nextElementSibling.querySelectorAll('video')].map(v=>({time:v.currentTime,muted:v.muted,paused:v.paused}))")
 assert max(x['time'] for x in sync)-min(x['time'] for x in sync)<.25
 page.evaluate("document.querySelectorAll('video').forEach(v=>v.pause());const v=document.querySelector('video[src=\"best_duel.mp4\"]');v.muted=true;v.play()")
 page.wait_for_function("document.querySelector('video[src=\"best_duel.mp4\"]').currentTime>2")
 featured_time=page.evaluate("const v=document.querySelector('video[src=\"best_duel.mp4\"]');v.pause();v.currentTime")
 page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(ROOT/'preview.png'))
 assert not errors,errors
 row=dict(status='PASS',url=URL,cases=3,cards=12,sync_groups=3,media=media,synced=sync,featured_played_to_s=featured_time,browser_errors=errors,screenshot='preview.png')
 (ROOT/'browser_verification.json').write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in row.items() if k!='media'}))
 browser.close()
