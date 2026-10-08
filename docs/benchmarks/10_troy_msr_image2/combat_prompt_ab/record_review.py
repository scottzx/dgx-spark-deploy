#!/usr/bin/env python3
"""Record the completed human visual review, bound to actual output hashes."""
import hashlib,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
# Authored after examining all twelve 21-frame contact sheets. These are human
# observations, not computed motion metrics or an automated quality classifier.
OBS = {
 'h3_old_01':('约1.5秒才刺矛；格挡后长时间架住兵器，约1.75–4秒动作变化很小，结尾仅再次移步。装备和前景人物较稳，背景交锋弱。',[1,0,0,1,2],1.5,2.25),
 'h3_old_02':('约1.5秒首次交锋；随后架住剑矛，约3.5秒才有第二次挥剑与后退。没有形成清楚的盾挡反击链；人物和装备较稳。',[1,1,1,1,2],1.5,1.5),
 'h3_old_03':('约1.25秒刺矛，稍后奥德修斯追进举剑；后半段多次停在交叉兵器姿态，接触和受力关系弱。装备较稳。',[1,1,0,1,2],1.25,1.5),
 'h3_new_01':('约0.5秒刺矛，随后拨开、追进斜劈、举盾抵挡、收剑并再次刺矛；三个阶段可读，兵器身份较稳。约2.2–3秒仍有持盾僵持，第二次刺矛的闪避/拨开不充分，受力反应偏弱。',[2,2,1,2,2],.5,1.0),
 'h3_new_02':('约0.75秒刺矛，接着追进斜劈和盾挡，后撤分离后再次刺矛；比同种子原版动作链完整。盾挡约2.25–3.25秒仍有停顿，最后的再次招架不清楚。',[2,2,1,2,2],.75,1.0),
 'h3_new_03':('约0.5–0.75秒开始刺矛，之后追进斜劈、盾挡、分离和再刺；比原版更早行动且往返更清楚。盾挡约2.25–3.5秒僵持，明显受力和第二次闪避仍不足。',[2,2,1,2,2],.75,1.25),
 'ltx_old_01':('约前2秒保持起势；之后守卫冲步、双方挥击。矛逐渐变成短刀/剑，握持和近身接触不稳定，缺少清楚的格挡受力。',[1,1,0,1,0],2.25,None),
 'ltx_old_02':('约1秒开始较大动作，之后有多次接近和分离；矛变短/变刀，奥德修斯左手出现盾牌，末段双方散开，镜头构图漂移。',[1,1,0,2,0],1.0,None),
 'ltx_old_03':('约1.25秒守卫开始挥击，后续双方多次挥刀和位移；原先的矛变成刀/剑，接触及受力关系不清楚，结尾停成对峙。',[1,1,0,1,0],1.25,None),
 'ltx_new_01':('约1秒开始大幅近身交战，明显早于同种子原版；双方绕转和连续挥击较多，但身体/装备互相遮混，矛变短刀、武器短暂消失或换手，动作逻辑不可靠。',[1,1,0,2,0],1.0,None),
 'ltx_new_02':('约1秒开始动作，与同种子原版接近；连续挥击、侧移和闪避较多，但矛变刀、盾牌变形/换位，身体反应与攻击不连贯。',[1,1,0,2,0],1.0,None),
 'ltx_new_03':('约1秒开始冲刺挥击，持续大步换位和再次进攻；活动量较大，但矛变剑/短刃，握持和盾牌形状变化，不能作为兵器一致的完整交锋镜头。',[1,1,0,2,0],1.0,None)
}
def main():
 m=json.loads((ROOT/'manifest.json').read_text());rows=[]
 score_keys=['contact','separation','reaction','footwork','weapon_integrity']
 for j in m['jobs']:
  n=f'{j["seed"]%100:02d}';note,scores,onset,hold=OBS[j['model']+'_'+j['variant']+'_'+n]
  r=json.loads((ROOT/'clips'/j['id']/'result.json').read_text());actual=sha(ROOT/'clips'/j['id']/'delivered.mp4')
  assert r['input_fingerprint']==j['input_fingerprint'] and r['media']['sha256']==actual
  rows.append(dict(id=j['id'],model=j['model'],variant=j['variant'],seed=j['seed'],input_fingerprint=j['input_fingerprint'],output_sha256=actual,
                   quality_status='partial_at_samples' if j['model']=='h3' else 'fail_at_samples',
                   production_approved=False,scores=dict(zip(score_keys,scores)),score_total=sum(scores),
                   first_attack_onset_s_approx=onset,longest_contact_hold_s_approx=hold,notes=note,
                   sample_count=21,dense_review_fps=12 if j['id']=='combat_ab_h3_new_2026100601' else None,
                   unmet=['precise impact reaction','fully continuous attack/defense'] if j['model']=='h3' else ['weapon identity/hands','precise impact reaction','specified spear/sword choreography'],
                   new_prompt_sequence_adherence='partial' if j['variant']=='new' else 'not_applicable'))
 paired=[]
 for model in ('h3','ltx'):
  for seed in (2026100601,2026100602,2026100603):
   old=next(x for x in rows if x['model']==model and x['seed']==seed and x['variant']=='old')
   new=next(x for x in rows if x['model']==model and x['seed']==seed and x['variant']=='new')
   paired.append(dict(model=model,seed=seed,old_score=old['score_total'],new_score=new['score_total'],
                      human_common_score_delta=new['score_total']-old['score_total'],
                      observation='earlier multi-stage combat; still weak impact and contact holds' if model=='h3' else 'more activity in some seeds; weapon integrity remains failed'))
 result=dict(manifest_fingerprint=m['fingerprint'],reviewer='human visual judgment by assistant',
             review_scope='21 timestamp samples per clip; featured candidate additionally inspected at12fps over the entire5s. Not full-frame or audio certification.',
             audio_reviewed=False,summary='H3＋连续攻防描述在三个种子都增加了攻防阶段，优于原描述的长时间架兵器；LTX改写后部分镜头更早活动，但六段均有兵器一致性问题。H3盾挡仍有停顿、受力和第二次闪避不足，完整成片验收尚未通过。',
             score_note='Five human ordinal0–2 criteria; descriptive within this small batch, not a standardized model benchmark. Approximate times are sampled visual observations.',
             clips=rows,paired=paired,featured_candidate='combat_ab_h3_new_2026100601',featured_is_production_approved=False,
             production_approved_ids=[],counts=dict(technical_pass=12,partial_at_samples=6,fail_at_samples=6,production_approved=0))
 (ROOT/'quality_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(result['counts']))
if __name__=='__main__':main()
