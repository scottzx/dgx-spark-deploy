#!/usr/bin/env python3
"""Collect measurements and render matched story comparisons from local results."""
import argparse
import json
from pathlib import Path
import statistics
import subprocess

from PIL import Image, ImageDraw

METHODS = ['generic','specific','ingredients','msr']
LABELS = ['H3 + generic LTX','H3 + shot-specific LTX','LTX Ingredients','LTX MSR V2']


def probe(path, frames):
    data = json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames',
        '-show_streams','-of','json',str(path)]))
    v = next(x for x in data['streams'] if x['codec_type']=='video')
    a = next(x for x in data['streams'] if x['codec_type']=='audio')
    assert int(v['nb_read_frames'])==frames and v['r_frame_rate']=='24/1', data
    assert a['channels']==2, data
    subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(path),'-f','null','-'],check=True)
    return dict(frames=frames,width=v['width'],height=v['height'],fps=24,
        duration_s=frames/24,sample_rate=int(a['sample_rate']),full_decode=True)


def sheet(rows, times, destination):
    canvas = Image.new('RGB',(336*len(times),222*len(rows)),'#151515')
    draw = ImageDraw.Draw(canvas)
    for i,(label,path) in enumerate(rows):
        draw.text((6,i*222+6),label,fill='white')
        for j,t in enumerate(times):
            temporary = destination.parent/f'.frame_{i}_{j}.png'
            subprocess.run(['ffmpeg','-y','-v','error','-ss',str(t),'-i',str(path),
                '-frames:v','1','-vf','scale=336:192:force_original_aspect_ratio=decrease,'
                'pad=336:192:(ow-iw)/2:(oh-ih)/2',str(temporary)],check=True)
            with Image.open(temporary) as im: canvas.paste(im,(336*j,222*i+26))
            temporary.unlink()
            draw.text((336*j+6,222*i+208),f'{t:.2f}s',fill='white')
    canvas.save(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    args = parser.parse_args();root = args.root.resolve()
    story = json.loads((root/'story.json').read_text())
    reports = {m:json.loads((root/m/'comparison.json').read_text()) for m in METHODS}
    for method in METHODS:
        reports[method]['local_media'] = probe(root/method/'film.mp4',story['frames'])
    # Center of each intended narrative beat; two extra moments per night beat.
    cursor = 0;times = []
    for shot in story['shots']:
        times.append((cursor+shot['delivered_frames']//2)/24)
        cursor += shot['delivered_frames']
    rows = [(label,root/method/'film.mp4') for label,method in zip(LABELS,METHODS)]
    sheet(rows,times,root/'story_comparison.png')
    night_start = sum(s['delivered_frames'] for s in story['shots'][:3])/24
    night_times = [night_start+t for t in [0.5,4,5.8,8,10,12.8]]
    sheet(rows,night_times,root/'night_comparison.png')
    cmd = ['ffmpeg','-y','-v','error']
    for _,path in rows: cmd += ['-i',str(path)]
    filters = []
    font = '/System/Library/Fonts/Supplemental/Arial.ttf'
    for i,label in enumerate(LABELS):
        filters.append(f'[{i}:v]setpts=N/(24*TB),scale=672:384:force_original_aspect_ratio=decrease,'
            'pad=672:384:(ow-iw)/2:(oh-ih)/2,pad=672:424:0:40:color=black,'
            f"drawtext=fontfile={font}:text='{label}':x=12:y=10:fontsize=18:fontcolor=white[v{i}]")
    filters += ['[v0][v1][v2][v3]xstack=inputs=4:layout=0_0|672_0|0_424|672_424[v]',
        '[1:a]asetpts=PTS-STARTPTS[a]']
    comparison = root/'four_methods_story.mp4'
    cmd += ['-filter_complex',';'.join(filters),'-map','[v]','-map','[a]',
        '-frames:v',str(story['frames']),'-c:v','libx264','-crf','19','-pix_fmt','yuv420p',
        '-c:a','aac','-ar','32000','-ac','2',str(comparison)]
    subprocess.run(cmd,check=True)
    comparison_media = probe(comparison,story['frames'])
    # Reduce native reports to auditable timing summaries without subjective scores.
    summaries = {}
    for method,report in reports.items():
        clips = report['clips']
        durations = [c.get('stage2_request_s',c.get('generation_s')) for c in clips]
        summaries[method] = dict(generation_s=sum(durations),
            per_shot_s=durations,median_per_shot_s=statistics.median(durations),
            video_duration_s=story['frames']/24,output=report['local_media'],
            shared_model_initialization_s=report.get('shared_model_initialization_s'),
            method_preparation_s=report.get('method_preparation_s'),
            h3_text_and_stage1_s=report.get('h3_text_and_stage1_s'),
            estimated_pipeline_compute_s=report.get('estimated_pipeline_compute_s'),
            peak_torch_allocated_gib=max(c['peak_torch_allocated_bytes'] for c in clips)/1024**3,
            timing_note=report.get('timing_note'))
        if method in ['ingredients','msr']:
            summaries[method]['denoising_loop_s'] = sum(c['phases_s']['denoising_loop_s'] for c in clips)
    native_file = root/'h3_native/native_decode.json'
    if native_file.exists():
        native = json.loads(native_file.read_text())
        clips = native['clips']
        # Downloaded native folders preserve case IDs; remote paths are audit metadata only.
        native_rows = []
        for shot,clip in zip(story['shots'],clips):
            source = root/'h3_native'/shot['case_id']/'h3_native.mp4'
            native_rows.append((shot['title'],source))
        # Three night clips together for Stage1-versus-Stage2 diagnosis.
        listing = root/'h3_native/night_concat.txt'
        listing.write_text(''.join(f"file '{path}'\n" for _,path in native_rows[3:]))
        night = root/'h3_native/night.mp4'
        subprocess.run(['ffmpeg','-y','-v','error','-f','concat','-safe','0','-i',str(listing),
            '-c:v','libx264','-crf','19','-c:a','aac','-ar','32000','-ac','2',str(night)],check=True)
        # Full masters have a daylight prefix; write the diagnostic sheet per row offset.
        native_canvas = Image.new('RGB',(336*6,222*3),'#151515')
        draw = ImageDraw.Draw(native_canvas)
        for i,(label,path,offset) in enumerate([('H3 native',night,0),
                ('H3 + generic',rows[0][1],night_start),
                ('H3 + specific',rows[1][1],night_start)]):
            draw.text((6,i*222+6),label,fill='white')
            for j,t in enumerate([0.5,3,4.8,7,10,12.8]):
                temporary = root/f'.native_{i}_{j}.png'
                subprocess.run(['ffmpeg','-y','-v','error','-ss',str(t+offset),'-i',str(path),
                    '-frames:v','1','-vf','scale=336:192',str(temporary)],check=True)
                with Image.open(temporary) as im: native_canvas.paste(im,(336*j,222*i+26))
                temporary.unlink()
        native_canvas.save(root/'native_night_comparison.png')
    result = dict(status='FILES_VERIFIED',methods=summaries,frames=story['frames'],
        comparison_media=comparison_media,quality_scoring='Manual narrative review, recorded separately; '
        'no biometric score or perceptual quality score inferred from decoding or resolution.')
    (root/'measurements.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
