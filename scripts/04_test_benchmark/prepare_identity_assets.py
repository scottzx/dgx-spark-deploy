#!/usr/bin/env python3
"""Prepare fixed model inputs by cropping the original board, without inventing detail."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageOps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    image = Image.open(args.board).convert('RGB')
    assert image.size == (1344, 768), image.size
    boxes = {
        'red_face': (365, 183, 470, 299), 'blue_face': (924, 247, 1025, 342),
        'red_body': (150, 177, 594, 721), 'blue_body': (817, 234, 1216, 710),
        'red_sword': (501, 207, 701, 357), 'blue_sword': (790, 189, 900, 386),
        'blue_shield': (967, 347, 1156, 542), 'setting': (473, 17, 928, 581),
    }
    crops = {}
    for name, box in boxes.items():
        crops[name] = image.crop(box)
        crops[name].save(args.output / f'{name}.png')
    # A person's close-up and complete costume share one reference slot.
    for color in ('red', 'blue'):
        canvas = Image.new('RGB', (768, 768), 'black')
        body = ImageOps.contain(crops[color+'_body'], (476, 736), Image.Resampling.LANCZOS)
        face = ImageOps.contain(crops[color+'_face'], (250, 300), Image.Resampling.LANCZOS)
        canvas.paste(body, (16, (768-body.height)//2))
        canvas.paste(face, (502, 32))
        canvas.save(args.output / f'{color}_identity.png')
    equipment = Image.new('RGB', (768, 768), 'black')
    for name, box in [('red_sword', (16,16,372,360)), ('blue_sword',(400,16,752,360)),
                      ('blue_shield',(220,390,548,752))]:
        part = ImageOps.contain(crops[name], (box[2]-box[0],box[3]-box[1]), Image.Resampling.LANCZOS)
        equipment.paste(part, (box[0],box[1]))
    equipment.save(args.output/'equipment.png')
    sheet = Image.new('RGB', (1536, 896), 'black')
    for name, box in [('red_identity',(0,0,512,640)),('blue_identity',(512,0,1024,640)),
                      ('equipment',(1024,0,1536,640)),('setting',(0,640,1536,896))]:
        source = Image.open(args.output/f'{name}.png')
        part = ImageOps.contain(source, (box[2]-box[0],box[3]-box[1]), Image.Resampling.LANCZOS)
        sheet.paste(part,(box[0]+(box[2]-box[0]-part.width)//2,box[1]+(box[3]-box[1]-part.height)//2))
    sheet.save(args.output/'ingredients_sheet.png')
    image.save(args.output/'board.png')
    manifest = dict(source=str(args.board.resolve()), source_sha256=hashlib.sha256(args.board.read_bytes()).hexdigest(),
        source_pixels=[1344,768], crops=boxes,
        roles={'red':'bearded, red cloak, bronze armor; right hand sword, left hand empty',
               'blue':'clean shaven, curly dark hair, blue cloak, bronze armor; right hand sword, left hand round shield'},
        note='Resizing crops does not create facial detail. The source provides one view, not a true turnaround.',
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.output.glob('*.png')})
    (args.output/'asset_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(status='PASS', files=len(manifest['files']),output=str(args.output))))


if __name__ == '__main__':
    main()
