#!/usr/bin/env python3
"""Create labeled visual comparisons from completed local identity trials."""
import argparse
from pathlib import Path
import subprocess
from PIL import Image,ImageDraw

def contact_sheet(rows,out,times):
 canvas=Image.new('RGB',(len(times)*336,len(rows)*230),'#151515')
 draw=ImageDraw.Draw(canvas)
 for row,item in enumerate(rows):
  label,path=item[:2]
  offset=item[2] if len(item)>2 else 0
  for k,t in enumerate(times):
   temporary=out.parent/f'.probe_{row}_{k}.png'
   subprocess.run(['ffmpeg','-y','-v','error','-ss',str(t+offset),'-i',str(path),'-frames:v','1',
    '-vf','scale=336:192',str(temporary)],check=True)
   with Image.open(temporary) as image:canvas.paste(image,(k*336,row*230+30))
   temporary.unlink()
  draw.text((6,row*230+8),label,fill='white')
 canvas.save(out)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
 args=p.parse_args();root=args.root.resolve()
 previous=root.parent/'07_troy_dual_workflows/troy_continuous.mp4'
 rows=[('Previous generic LTX',previous),
  ('Same H3 capture - identity-specific LTX',root/'specific_refiner/delivery/refined_1344x768_121f.mp4'),
  ('Ingredients - fresh native LTX generation',root/'ingredients/trial.mp4'),
  ('MSR V2 - fresh native LTX generation',root/'msr/trial.mp4')]
 contact_sheet(rows,root/'four_methods_contact_sheet.png',[0,1,2,3,4])
 contact_sheet([('Optimized storyboard',root/'optimized_workflows/storyboard.mp4'),
  ('Optimized continuation',root/'optimized_workflows/continuous.mp4')],
  root/'optimized_workflows/contact_sheet.png',[0,2,4,5.1,8.4])
 contact_sheet([('Ref2VA native close shot',root/'ref_native/identity_ref_new_angle/h3_native.mp4'),
  ('Ref2VA generic LTX close shot',root/'ref2va/storyboard.mp4',121/24),
  ('Ref2VA identity-specific LTX close shot',root/'optimized_workflows/storyboard.mp4',121/24)],
  root/'close_shot_comparison.png',[0,1,2,3,4])
 cmd=['ffmpeg','-y','-v','error'];filters=[]
 titles=['Previous generic LTX','Identity-specific LTX / same H3 latent','Ingredients / fresh generation','MSR V2 / fresh generation']
 for i,(_,path) in enumerate(rows):
  cmd+=['-i',str(path)]
  filters.append(f'[{i}:v]trim=end_frame=121,setpts=N/(24*TB),scale=672:384:force_original_aspect_ratio=decrease,'
   f'pad=672:384:(ow-iw)/2:(oh-ih)/2,pad=672:424:0:40:color=black,'
   f"drawtext=fontfile=/System/Library/Fonts/Supplemental/Arial.ttf:text='{titles[i]}':x=12:y=10:fontsize=18:fontcolor=white[v{i}]")
 filters.append('[v0][v1][v2][v3]xstack=inputs=4:layout=0_0|672_0|0_424|672_424[v]')
 filters.append('[1:a]atrim=end_sample=161333,asetpts=PTS-STARTPTS[a]')
 cmd+=['-filter_complex',';'.join(filters),'-map','[v]','-map','[a]','-frames:v','121',
  '-c:v','libx264','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-ar','32000','-ac','2',str(root/'four_methods_comparison.mp4')]
 subprocess.run(cmd,check=True)

if __name__=='__main__':main()
