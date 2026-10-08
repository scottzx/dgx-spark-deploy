#!/usr/bin/env python3
"""Keep the whole story while removing three observed continuity-breaking tails."""
import hashlib,json
from pathlib import Path
from build_review import ROOT,assemble,sha,save
def main():
    selection=json.loads((ROOT/'selection.json').read_text());jobs=[];frame=0
    endings={'S09':48,'S11':60,'S17':42}
    reasons={'S09':'Cut before reaching the ground, preserving the continuation into the dedicated S10 descent.','S11':'Keep the signal, cut before turning and walking back toward the horse.','S17':'Keep the closed-gate army waiting insert; cut before H3 opens the gate prematurely.'}
    for source in selection['selected']:
        assert sha(ROOT/source['clip_path'])==source['sha256']
        n=endings.get(source['id'],120)
        jobs.append(dict(id=source['id'],model=source['model'],clip_path=source['clip_path'],source_sha256=source['sha256'],edit_in_frame=0,edit_frames=n,start_frame=frame,end_frame=frame+n,start_s=frame/24,end_s=(frame+n)/24,reason=reasons.get(source['id'],'Use the full newly generated shot.')))
        frame+=n
    plan=dict(base_manifest_fingerprint=selection['base_manifest_fingerprint'],repair_manifest_fingerprint=selection['repair_manifest_fingerprint'],fps=24,frames=frame,duration_s=frame/24,model_counts=selection['model_counts'],jobs=jobs)
    plan['fingerprint']=hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(',',':')).encode()).hexdigest();save('edit_plan.json',plan)
    verification=json.loads((ROOT/'assembly_verification.json').read_text())
    uncut_receipt=verification.get('uncut_film',verification['film'])
    original=ROOT/'film_uncut_100s.mp4'
    if not original.exists():
        assert sha(ROOT/'film.mp4')==verification['film']['sha256']
        (ROOT/'film.mp4').rename(original)
    assert sha(original)==uncut_receipt['sha256']
    uncut=dict(uncut_receipt,path=original.name)
    film=assemble(jobs,ROOT/'film.mp4');battle=assemble(jobs[13:],ROOT/'battle.mp4')
    verification.update(film=film,battle_excerpt=battle,uncut_film=uncut,edit_plan_fingerprint=plan['fingerprint']);save('assembly_verification.json',verification)
    status=json.loads((ROOT/'run_status.json').read_text());status.update(film=film,battle_excerpt=battle,uncut_film=uncut,edit_plan_fingerprint=plan['fingerprint']);save('run_status.json',status)
    selection.update(edit_plan_fingerprint=plan['fingerprint'],edited_duration_s=film['duration_s']);save('selection.json',selection)
    text=(ROOT/'review.html').read_text()
    text=text.replace('完整100秒','完整91.25秒（另保留100秒未剪版）').replace('完整影片 · 100秒','完整影片 · 91.25秒').replace('守军拦截至广场大战 · 35秒','守军拦截至广场大战 · 31.75秒').replace('src="battle_35s.mp4"','src="battle.mp4"')
    text=text.replace('与上一版完整片同步比较','100秒未剪版与上一版同步比较').replace('左为本轮混合流程，右为上一版LTX MSR完整片。','左为本轮100秒未剪素材，右为上一版LTX MSR完整片；两者都按20×5秒对齐。')
    text=text.replace('<div class="grid" id="comparison"><video muted controls preload="metadata" playsinline src="film.mp4">','<div class="grid" id="comparison"><video muted controls preload="metadata" playsinline src="film_uncut_100s.mp4">')
    text=text.replace('<h2>逐镜结果</h2>','<h2>逐镜原始素材</h2><p>以下播放器保留每镜完整5秒。成片缩短S09、S11和S17，避开重复落地、转回木马和提前开门；实际剪辑段落见<a href="edit_plan.json">剪辑记录</a>。</p>')
    base=json.loads((ROOT/'manifest.json').read_text())
    for j,old in zip(jobs,base['jobs']):
        text=text.replace(f'<p>{old["start_s"]}–{old["end_s"]}秒 · 新生成 · 种子',f'<p>成片{j["start_s"]:g}–{j["end_s"]:g}秒 · 选入{j["edit_frames"]/24:g}秒 / 原始5秒 · 种子')
    (ROOT/'review.html').write_text(text)
    print(json.dumps({'status':'PASS','film':film,'battle':battle,'uncut':uncut}))
if __name__=='__main__':main()
