#!/usr/bin/env python3
"""Prepare user-authorized generated drivers for the three-product Wan test."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path('/home/admin/wan-animate2-runtime')
PREVIOUS=Path('/home/admin/digital-human-runtime')
OUT=ROOT/'inputs/products';OUT.mkdir(parents=True,exist_ok=True)
shutil.copy2(PREVIOUS/'inputs/product_actions/table.png',OUT/'reference.png')
cases=[('original','原味','左侧红底白字的原味可口可乐罐'),
       ('diet','健怡','中间银底红字的健怡可口可乐罐'),
       ('zero','零度','右侧红底黑字的零度可口可乐罐')]
jobs=[];receipts=[]
for name,label,appearance in cases:
    source=PREVIOUS/'outputs/product_actions_ltx'/name/'motion.mp4'
    driver=OUT/f'{name}_driver.mp4';shutil.copy2(source,driver)
    prompt=('人物外观描述：一位成年中国女性，齐肩黑色直发，穿红色长袖上衣，坐在浅灰色桌后，面向镜头。'
            '背景描述：柔和均匀的摄影棚灯光，灰色背景，固定中景镜头。桌上有三罐商品：左边红白原味罐、中间银红健怡罐、右边红黑零度罐。'
            f'动作描述：跟随参照视频的连续动作，双手开始为空，拿起{appearance}，举至胸前，正面朝向镜头，手持介绍，随后将同一罐放回原位，松开手，空手自然放在桌上。'
            '另外两罐始终在桌上。手与罐保持合理接触，商品形状、颜色、图案和人物面貌保持一致，不增加商品，不切镜头。')
    prompt_file=OUT/f'{name}_prompt.txt';prompt_file.write_text(prompt+'\n')
    jobs.append({'product':name,'reference':str(OUT/'reference.png'),'driving':str(driver),'prompt_file':str(prompt_file)})
    probe=json.loads(subprocess.run(['/home/admin/.local/bin/ffprobe','-v','error','-count_frames','-show_streams','-of','json',str(driver)],check=True,capture_output=True,text=True).stdout)
    video=next(s for s in probe['streams'] if s['codec_type']=='video')
    assert int(video['nb_read_frames'])==201 and abs(float(video['duration'])-8.04)<.01
    receipts.append({'product':name,'label':label,'source':str(source),'driver':str(driver),
                     'driver_sha256':hashlib.sha256(driver.read_bytes()).hexdigest(),
                     'frames':201,'fps':25,'duration_seconds':8.04,'size':[video['width'],video['height']],
                     'input_kind':'generated_product_video',
                     'authorization':'User explicitly authorized using the existing generated videos because no real capture is available.',
                     'scope':'Generated motion drivers can carry their existing hand, can, and packaging errors into Wan results.'})
(OUT/'batch.json').write_text(json.dumps(jobs,ensure_ascii=False,indent=2)+'\n')
(OUT/'sources.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'products':3,'batch':str(OUT/'batch.json'),'input_kind':'generated_product_video'},ensure_ascii=False))
