"""Temporal false positives, isolation and API replay/storage contracts."""
import io
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from PIL import Image
from fastapi.testclient import TestClient

from temporal import StreamConsensus


def reading(plate='51A12345', bbox=None, review=False):
    return {'plate': plate, 'valid_format': True, 'needs_review': review,
            'bbox': bbox or [10, 10, 90, 50]}


class StreamChecks(unittest.TestCase):
    def test_voting_isolation_and_bad_frames(self):
        tracker = StreamConsensus()
        session = tracker.session('a')
        for index, plate in enumerate(['51A12345','51A12346','51A12345','51A12345']):
            item = reading(plate)
            tracker.update(session, [item], index*.2, 100, 60)
            self.assertEqual(item['temporal']['status'], 'stable' if index == 3 else 'pending')
        tracker.mark_saved(session, item, .6)
        item = reading(); tracker.update(session, [item], 31., 100, 60)
        self.assertEqual(item['temporal']['status'], 'pending', 'Long gaps must not reuse previous votes')
        isolated = tracker.session('b')
        for index in range(8):
            item = reading(review=True)
            tracker.update(isolated, [item], index*.2, 100, 60)
            self.assertEqual(item['temporal']['status'], 'review')
            self.assertFalse(item['temporal']['new_event'])
        self.assertLessEqual(len(isolated['tracks'][0]['votes']), 7)
        pair = tracker.session('pair')
        for index in range(3):
            a, b = reading(bbox=[1,1,30,20]), reading('29C12345', [60,1,90,20])
            tracker.update(pair, [a,b], index*.2, 100, 60)
        self.assertNotEqual(a['temporal']['track_id'], b['temporal']['track_id'])
        self.assertEqual([a['temporal']['plate'], b['temporal']['plate']], ['51A12345','29C12345'])
        moving = tracker.session('moving')
        track_ids = []
        for index,x in enumerate([100,80,55,25]):
            item = reading(bbox=[x,10,x+50,40])
            tracker.update(moving,[item],index*.2,200,60)
            track_ids.append(item['temporal']['track_id'])
        self.assertEqual(len(set(track_ids)),1,'Predict movement instead of restarting a fast-moving plate track')
        self.assertEqual(item['temporal']['status'],'stable')
        crossing = tracker.session('crossing')
        for index in range(3):
            a,b=reading(bbox=[0,0,40,20]),reading('29C12345',[20,0,60,20])
            tracker.update(crossing,[a,b],index*.2,100,60)
        ambiguous = reading(bbox=[10,0,50,20])
        tracker.update(crossing,[ambiguous],.6,100,60)
        self.assertNotIn(ambiguous['temporal']['track_id'],[a['temporal']['track_id'],b['temporal']['track_id']])
        self.assertEqual(ambiguous['temporal']['status'],'pending')

    def test_api_idempotency_and_one_saved_event(self):
        import app as module
        class Engine:
            multiple = False
            def predict(self, image, confidence=.35):
                item={**reading(), 'raw_text':'51A12345', 'display_plate':'51A-123.45',
                         'detector_confidence':.95, 'ocr_confidence':.99, 'layout':'one_line',
                         'crop':image[10:50,10:90]}
                return [item,{**item,'bbox':[1,1,8,8]}] if self.multiple else [item]
        original = module.DATA, module.API_KEY, getattr(module.app.state,'engine',None)
        with tempfile.TemporaryDirectory() as folder:
            module.DATA, module.API_KEY, module.app.state.engine = Path(folder), 'test-key', Engine()
            buffer = io.BytesIO(); Image.new('RGB',(100,60),'white').save(buffer,format='PNG')
            files = {'file':('x.png',buffer.getvalue(),'image/png')}
            stream = str(uuid.uuid4())
            try:
                with TestClient(module.app) as client:
                    client.headers['X-API-Key']='test-key'
                    def send(moment, **data):
                        return client.post('/api/recognize',files=files,data={'stream_id':stream,'sample_time':moment,**data})
                    self.assertEqual(send('nan').status_code,422)
                    self.assertEqual(client.post('/api/recognize',files=files,data={'stream_id':'wrong','sample_time':0}).status_code,422)
                    self.assertEqual(client.post('/api/recognize',files=files,data={'stream_id':stream}).status_code,422)
                    send(0);send(.2)
                    with patch.object(module,'jpeg_bytes',side_effect=OSError('Storage unavailable')):
                        with self.assertRaises(OSError): send(.4)
                    self.assertEqual(client.get('/api/history').json()['total'],0)
                    for index in range(2,10):
                        response = send(index*.2)
                        self.assertEqual(response.status_code,200)
                    self.assertEqual(client.get('/api/history').json()['total'],1)
                    self.assertFalse(response.json()['detections'][0]['saved'])
                    self.assertEqual(send(1.8).json()['request_id'],response.json()['request_id'])
                    self.assertEqual(send(1.8,source='changed').status_code,409)
                    self.assertEqual(send(.5).status_code,409)
                    self.assertEqual(client.get('/api/history').json()['total'],1)
                    for index in range(3): send(40+index*.2)
                    self.assertEqual(client.get('/api/history').json()['total'],2)
                    self.assertEqual(len(list((Path(folder)/'images').glob('*.jpg'))),4)
                    # A still-visible track is not saved again after the 30-second cooldown.
                    for index in range(100): send(41+index*.5)
                    self.assertEqual(client.get('/api/history').json()['total'],2)
                    stream=str(uuid.uuid4());module.app.state.engine.multiple=True
                    for index in range(3): send(index*.2)
                    self.assertEqual(client.get('/api/history').json()['total'],3,'Identical plate detections in one frame save only one event')
            finally:
                module.DATA, module.API_KEY, module.app.state.engine = original


if __name__ == '__main__':
    unittest.main()
