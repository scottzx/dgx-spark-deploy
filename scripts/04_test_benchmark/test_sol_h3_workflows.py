"""Run on Spark with stage1-env; CPU checks against the real pinned packing ABI."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, '/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark')
sys.path.insert(0, '/home/admin/sol-spark-runtime/sources/FastVideo')
if os.environ.get('SOL_WORKFLOW_TEST_OVERLAY'):
    sys.path.insert(0, os.environ['SOL_WORKFLOW_TEST_OVERLAY'])

import torch
from fastvideo.pipelines.basic.minimax_h3 import packing
from fastvideo.pipelines.basic.minimax_h3.stages import minimax_h3_denoising as denoise_module
from runtime.stage1_ops import continuation
from runtime.workflows import validate_workflow, prepare_case
from runtime.config import normalize_case


class WorkflowTests(unittest.TestCase):
    def test_ref2va_preserves_native_positions_and_conditions(self):
        from fastvideo.pipelines.basic.minimax_h3.reference import MiniMaxH3PreparedReference
        refs=[MiniMaxH3PreparedReference('image',latent_height=16,latent_width=16),
              MiniMaxH3PreparedReference('video',has_audio=True,num_latent_frames=2,
                  latent_height=24,latent_width=32,num_audio_latents=9,block_timestamps=[0.,1.]),
              MiniMaxH3PreparedReference('audio',has_audio=True,num_audio_latents=6)]
        old=packing.build_ref2va_packed_sequence(torch.ones(10,dtype=torch.long),refs,
            37,24,42,207,(1,2,2))
        layout,clean=continuation.build_layout(old,7,40,[0,1,5,9,13,17,18],19,False,True)
        for modality,prefix in [('video',clean),('audio',80)]:
            indices=getattr(old,modality+'_indices')
            new_indices=getattr(layout,modality+'_indices')
            count=getattr(old,'num_condition_'+modality+'_rows')
            self.assertTrue(torch.equal(old.position_ids[indices],layout.position_ids[new_indices[prefix:]]))
            self.assertEqual(getattr(layout,'num_condition_'+modality+'_rows'),prefix+count)
        indices=torch.cat((layout.text_indices,layout.video_indices,layout.audio_indices))
        self.assertTrue(torch.equal(indices.sort().values,torch.arange(layout.sequence_length)))
        validate_workflow(dict(task='ref2va',transition='continue',previous_clip_id='a'))

    def test_delivered_endpoint_profiles(self):
        self.assertEqual(continuation.window_geometry(37, 22, 124, 121),
            (30, 7, 19, [0, 1, 5, 9, 13, 17, 18]))
        self.assertEqual(continuation.window_geometry(72, 22, 243, 241)[2], 20)
        with self.assertRaises(ValueError):
            continuation.window_geometry(36, 22, 124, 121)

    def test_ref2va_continuation_keeps_values_and_detects_changed_reference(self):
        from fastvideo.pipelines.basic.minimax_h3.reference import MiniMaxH3PreparedReference
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            path=root/'continuation_state.pt'
            torch.save(dict(video=torch.ones(1,24,37,24,42),audio=torch.ones(2,64,207)),path)
            (root/'capture.json').write_text(json.dumps(dict(status='PASS',stage1_frames=124,
                emit_frames=121,continuation_state_sha256=hashlib.sha256(path.read_bytes()).hexdigest())))
            old=packing.build_ref2va_packed_sequence(torch.ones(10,dtype=torch.long),
                [MiniMaxH3PreparedReference('image',latent_height=16,latent_width=16),
                 MiniMaxH3PreparedReference('audio',has_audio=True,num_audio_latents=6)],
                37,24,42,207,(1,2,2))
            state=dict(task='ref2va',case={'case':dict(transition='continue',
                previous_capture_dir=str(root),references=[{},{}])})
            args=SimpleNamespace(pipeline_config=SimpleNamespace(dit_config=SimpleNamespace(patch_size=(1,2,2))))
            corrupt=[False]
            def prepare(batch,args):
                batch.extra['minimax_h3_layout']=old
                batch.latents=torch.zeros(old.video_indices.numel(),96)
                batch.latents[:old.num_condition_video_rows]=17
                batch.audio_latents=torch.zeros(old.audio_indices.numel(),64)
                batch.audio_latents[:old.num_condition_audio_rows]=23
                return batch
            def denoise(batch,args):
                layout=batch.extra['minimax_h3_layout']
                unique,inverse=denoise_module.build_row_timesteps(layout,video_timestep=.5,audio_timestep=.5,
                    condition_video_timestep=.999,condition_audio_timestep=1.)
                clean=7*252
                rows=unique[inverse][layout.video_indices]
                self.assertTrue(torch.all(rows[:clean]==1.))
                self.assertTrue(torch.all(rows[clean:layout.num_condition_video_rows]==.999))
                self.assertTrue(torch.all(batch.latents[clean:layout.num_condition_video_rows]==17))
                self.assertTrue(torch.all(batch.audio_latents[80:layout.num_condition_audio_rows]==23))
                batch.latents[layout.num_condition_video_rows:]+=1
                batch.audio_latents[layout.num_condition_audio_rows:]+=1
                if corrupt[0]: batch.latents[clean,0]+=1
                return batch
            stages={'latent_preparation_stage':SimpleNamespace(forward=prepare),
                'denoising_stage':SimpleNamespace(forward=denoise)}
            worker=SimpleNamespace(_sol_h3_stage1=state,pipeline=SimpleNamespace(_stage_name_mapping=stages))
            original=denoise_module.build_row_timesteps
            try:
                continuation.install(worker)
                for broken in (False,True):
                    corrupt[0]=broken
                    batch=stages['latent_preparation_stage'].forward(SimpleNamespace(extra={}),args)
                    if broken:
                        with self.assertRaisesRegex(RuntimeError,'Pinned continuation'):
                            stages['denoising_stage'].forward(batch,args)
                    else:
                        stages['denoising_stage'].forward(batch,args)
                        self.assertTrue(state['continuation_audit']['frozen_prefix_verified'])
                        self.assertEqual(state['continuation_audit']['reference_video_rows_preserved'],64)
                        self.assertEqual(state['continuation_audit']['reference_audio_rows_preserved'],12)
            finally:
                denoise_module.build_row_timesteps=original

    def test_invalid_request_before_worker(self):
        for case in [dict(transition='independent', previous_clip_id='a'),
                     dict(transition='continue', previous_clip_id='../a'),
                     dict(transition='continue', previous_clip_id='a', first_frame='x'),
                     dict(transition='continue', previous_clip_id='a', audio_context_frames=22)]:
            with self.assertRaises(ValueError):
                validate_workflow(case)
        valid = normalize_case(dict(case_id='b', prompt='A duel', task='fl2va',
            transition='continue', previous_clip_id='a'))
        self.assertEqual(valid['previous_clip_id'], 'a')
        with self.assertRaises(ValueError):
            prepare_case(SimpleNamespace(report={'requests': []}), valid)

    def test_layout_target_positions_and_stereo(self):
        old = packing.build_packed_sequence(torch.ones(10, dtype=torch.long), 37, 24, 42, 207,
            (1, 2, 2), ('first', 'last'))
        layout, clean = continuation.build_layout(old, 7, 40, [0,1,5,9,13,17,18], 19, True)
        self.assertEqual(clean, 7*12*21)
        self.assertEqual(layout.num_condition_audio_rows, 80)
        self.assertTrue(torch.equal(old.position_ids[old.video_indices[old.num_condition_video_rows:]],
            layout.position_ids[layout.video_indices[layout.num_condition_video_rows:]]))
        self.assertTrue(torch.equal(old.position_ids[old.audio_indices],
            layout.position_ids[layout.audio_indices[80:]]))
        pinned = layout.position_ids[layout.audio_indices[:80]]
        self.assertNotEqual(float(pinned[0,2]), float(pinned[40,2]))
        self.assertEqual(float(pinned[0,0]), 10 + 32 - 40)
        indices = torch.cat((layout.text_indices, layout.video_indices, layout.audio_indices))
        self.assertTrue(torch.equal(indices.sort().values, torch.arange(layout.sequence_length)))

    def test_independent_continue_independent_frozen_conditions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video = torch.arange(37.).view(1,1,37,1,1).expand(1,24,37,24,42).clone()
            audio = torch.arange(207.).view(1,1,207).expand(2,64,207).clone()
            path = root/'continuation_state.pt'
            torch.save(dict(video=video,audio=audio), path)
            (root/'capture.json').write_text(json.dumps(dict(status='PASS', stage1_frames=124,
                emit_frames=121, continuation_state_sha256=hashlib.sha256(path.read_bytes()).hexdigest())))
            state = dict(task='fl2va',case={'case':{}})
            args = SimpleNamespace(pipeline_config=SimpleNamespace(dit_config=SimpleNamespace(patch_size=(1,2,2))))
            def prepare(batch,args):
                batch.extra['minimax_h3_layout'] = packing.build_packed_sequence(torch.ones(10,dtype=torch.long),
                    37,24,42,207,(1,2,2),('first',))
                batch.latents = torch.zeros((38*252,96))
                batch.audio_latents = torch.zeros((414,64))
                return batch
            def denoise(batch,args):
                layout=batch.extra['minimax_h3_layout']
                u, inv=denoise_module.build_row_timesteps(layout,video_timestep=.5,audio_timestep=.5,
                    condition_video_timestep=.999,condition_audio_timestep=1.)
                if state['case']['case'].get('transition')=='continue':
                    self.assertTrue(torch.all(u[inv][layout.video_indices[:7*252]]==1.))
                batch.latents[layout.num_condition_video_rows:]+=1
                batch.audio_latents[layout.num_condition_audio_rows:]+=1
                return batch
            stages={'latent_preparation_stage':SimpleNamespace(forward=prepare),
                    'denoising_stage':SimpleNamespace(forward=denoise)}
            worker=SimpleNamespace(_sol_h3_stage1=state,pipeline=SimpleNamespace(_stage_name_mapping=stages))
            original=denoise_module.build_row_timesteps
            try:
                continuation.install(worker)
                for transition in ('independent','continue','independent'):
                    state['case']['case']=dict(transition=transition,previous_capture_dir=str(root),
                        context_frames=22,audio_context_frames=24)
                    batch=SimpleNamespace(extra={})
                    batch=stages['latent_preparation_stage'].forward(batch,args)
                    batch=stages['denoising_stage'].forward(batch,args)
                    if transition=='continue':
                        self.assertTrue(state['continuation_audit']['frozen_prefix_verified'])
                        self.assertEqual(float(batch.audio_latents[0,0]),162.)
                        self.assertEqual(float(batch.audio_latents[39,0]),201.)
                    else:
                        self.assertIsNone(state['continuation_audit'])
                        self.assertEqual(batch.extra['minimax_h3_layout'].num_condition_audio_rows,0)
            finally:
                denoise_module.build_row_timesteps=original


if __name__ == '__main__':
    unittest.main(verbosity=2)
