"""Route integration using real delivered clips and FFmpeg, without GPU reload."""
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import unittest

from run_troy_workflow_comparison import validate

spec = importlib.util.spec_from_file_location('sol_api_review', '/home/admin/sol-spark-runtime/sol_api_server.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
root = Path('/home/admin/sol-spark-runtime/outputs/troy_dual_workflows_20261003_v2')
report = json.loads((root / 'comparison.json').read_text())
board = '/home/admin/sol-spark-runtime/inputs/troy_workflows_20261003/board_01.png'
board2 = '/home/admin/sol-spark-runtime/inputs/troy_workflows_20261003/board_02.png'


class RecordedPipeline:
    task = 'fl2va'

    def __init__(self):
        self.cases = []

    def generate(self, case, mode):
        self.cases.append(copy.deepcopy(case))
        source = report['shots'][1 if case['transition'] == 'continue' else 0]
        return dict(case_id=case['case_id'], output=source['video_path'],
            delivered_frames=source['delivered_frames'], delivered_duration_s=source['delivered_duration_s'],
            transition=case['transition'])


class StoryAPI(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        api.pipeline_instance = RecordedPipeline()
        api.server_state['status'] = 'READY'
        api.pipeline_lock = asyncio.Lock()

    async def test_mixed_workflows_real_frame_assembly(self):
        req = api.StoryRequest(story_id='routing_mixed', initial_frame=board, shots=[
            api.ShotItem(shot_id='a', prompt='A duel', transition='independent'),
            api.ShotItem(shot_id='b', prompt='Continue the duel', transition='continue'),
            api.ShotItem(shot_id='c', prompt='New angle', transition='independent', first_frame=board2)])
        response = await api.generate_chained_story(req)
        a, b, c = api.pipeline_instance.cases
        self.assertEqual(b['previous_clip_id'], a['case_id'])
        self.assertNotIn('first_frame', b)
        self.assertNotIn('previous_clip_id', c)
        self.assertEqual(c['first_frame'], board2)
        self.assertEqual(response['delivered_frames'], 344)
        validate(Path(response['video_path']), 344)

    async def test_legacy_tail_frame_contract(self):
        req = api.StoryRequest(story_id='routing_legacy', initial_frame=board, shots=[
            api.ShotItem(shot_id='a', prompt='A duel'), api.ShotItem(shot_id='b', prompt='A duel continues')])
        response = await api.generate_chained_story(req)
        a, b = api.pipeline_instance.cases
        self.assertEqual(a['first_frame'], board)
        self.assertTrue(Path(b['first_frame']).is_file())
        self.assertTrue(b['first_frame'].endswith('_tail.png'))
        self.assertEqual(b['transition'], 'independent')
        validate(Path(response['video_path']), 242)

    async def test_first_shot_cannot_continue(self):
        req = api.StoryRequest(story_id='routing_invalid', initial_frame=board, shots=[
            api.ShotItem(shot_id='a', prompt='A duel', transition='continue')])
        with self.assertRaises(api.HTTPException) as raised:
            await api.generate_chained_story(req)
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(api.pipeline_instance.cases, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
