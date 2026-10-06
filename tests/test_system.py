"""Small independent contract checks. Fake inference isolates API/storage; real inference has its own report."""
import io
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recognition import decode_image, flatten_two_lines, format_plate, is_vietnamese_plate, normalize_plate
from scripts.prepare_data import polygon_to_box
from scripts.evaluate_robustness import iou
from scripts.evaluate_ocr import distance


class Contracts(unittest.TestCase):
    def test_image_and_text_boundaries(self):
        self.assertEqual(normalize_plate('51a-123.45'), '51A12345')
        self.assertEqual(format_plate('51A12345'), '51A-123.45')
        self.assertTrue(is_vietnamese_plate('59X112345'))
        self.assertFalse(is_vietnamese_plate('HELLO'))
        for data in (b'', b'not an image', b'<svg></svg>'):
            with self.assertRaises(ValueError):
                decode_image(data)
        image = Image.new('RGB', (100, 60), 'white')
        buffer = io.BytesIO(); image.save(buffer, format='PNG')
        self.assertEqual(decode_image(buffer.getvalue()).shape, (60, 100, 3))
        self.assertGreater(flatten_two_lines(np.full((60, 100, 3), 255, dtype=np.uint8)).shape[1], 100)
        self.assertEqual(iou([0, 0, 10, 10], [0, 0, 10, 10]), 1)
        self.assertEqual(iou([0, 0, 10, 10], [20, 20, 30, 30]), 0)
        self.assertEqual(distance('51A12345', '51A12345'), 0)
        self.assertEqual(distance('51A12345', '51A12346'), 1)
        self.assertEqual(distance('ABC', ''), 3)
        self.assertEqual(polygon_to_box('1 .2 .3 .6 .3 .6 .7 .2 .7'), '1 0.40000000 0.50000000 0.40000000 0.40000000')
        with self.assertRaises(ValueError):
            polygon_to_box('1 -1 .3 .6 .3 .6 .7')

    def test_api_storage_and_auth(self):
        import app as module

        class Engine:
            def predict(self, image, confidence=.35):
                return [{'plate': '51A12345', 'raw_text': '51A12345', 'display_plate': '51A-123.45',
                         'bbox': [10, 10, 90, 50], 'detector_confidence': .95, 'ocr_confidence': .9,
                         'needs_review': False, 'valid_format': True, 'layout': 'one_line', 'crop': image[10:50, 10:90]}]

        original_data, original_key = module.DATA, module.API_KEY
        with tempfile.TemporaryDirectory() as folder:
            module.DATA, module.API_KEY = Path(folder), 'test-key'
            module.app.state.engine = Engine()
            image = Image.new('RGB', (100, 60), 'white')
            data = io.BytesIO(); image.save(data, format='PNG')
            try:
                with TestClient(module.app) as client:
                    self.assertEqual(client.get('/api/history').status_code, 401)
                    client.headers['X-API-Key'] = 'test-key'
                    self.assertEqual(client.post('/api/recognize', files={'file': ('x.png', b'bad')}).status_code, 400)
                    self.assertEqual(client.post('/api/recognize', files={'file': ('x.png', data.getvalue())}, data={'confidence': 'nan'}).status_code, 422)
                    self.assertEqual(client.get('/api/history?since=2026-01-01').status_code, 400)
                    self.assertEqual(client.post('/api/recognize', content=b'x', headers={'Content-Length': str(11*1024*1024)}).status_code, 413)
                    response = client.post('/api/recognize', files={'file': ('x.png', data.getvalue())}, data={'source': '=1+1'} )
                    self.assertEqual(response.status_code, 200)
                    item = response.json()['detections'][0]
                    self.assertEqual(client.get(item['crop_url']).status_code, 200)
                    self.assertEqual(client.get('/api/history?plate=51A-123.45').json()['total'], 1)
                    self.assertEqual(client.get('/api/history?plate=99B').json()['total'], 0)
                    self.assertIn("'=1+1", client.get('/api/history.csv').text)
                    client.post('/api/recognize', files={'file': ('x.png', data.getvalue())}, data={'save': 'false'})
                    self.assertEqual(client.get('/api/history').json()['total'], 1)
                    self.assertEqual(client.delete('/api/history/' + item['id']).status_code, 200)
                    self.assertEqual(client.get(item['crop_url']).status_code, 404)
                    self.assertEqual(client.get('/api/history').json()['total'], 0)
                    entry = client.post('/api/recognize', files={'file': ('entry.png', data.getvalue())}).json()['detections'][0]
                    event = {'record_id': entry['id'], 'plate': '51A-123.46', 'direction': 'in', 'confirmed': False}
                    self.assertEqual(client.post('/api/parking/events', json=event).status_code, 422)
                    event['confirmed'] = True
                    entered = client.post('/api/parking/events', json=event)
                    self.assertEqual(entered.status_code, 200)
                    self.assertEqual(entered.json()['session']['entry_corrected'], 1)
                    self.assertEqual(client.get('/api/parking').json()['inside'], 1)
                    self.assertEqual(client.delete('/api/history/' + entry['id']).status_code, 409)
                    self.assertEqual(client.post('/api/parking/events', json=event).status_code, 409)
                    exit_record = client.post('/api/recognize', files={'file': ('exit.png', data.getvalue())}).json()['detections'][0]
                    event['record_id'] = exit_record['id']
                    self.assertEqual(client.post('/api/parking/events', json=event).status_code, 409)
                    event.update(direction='out', plate='51A-999.99')
                    self.assertEqual(client.post('/api/parking/events', json=event).status_code, 409)
                    event['plate'] = '51A-123.46'
                    exited = client.post('/api/parking/events', json=event)
                    self.assertEqual(exited.status_code, 200)
                    self.assertEqual(exited.json()['session']['status'], 'closed')
                    self.assertGreaterEqual(exited.json()['session']['duration_seconds'], 0)
                    parking = client.get('/api/parking?status=all').json()
                    self.assertEqual(parking['inside'], 0)
                    self.assertEqual(parking['items'][0]['plate'], '51A12346')
                    self.assertTrue(parking['items'][0]['entry_image_url'])
                    self.assertEqual(client.get('/api/history?plate=51A12345').json()['total'], 2)
                    arrivals = [client.post('/api/recognize', files={'file': ('race.png', data.getvalue())}).json()['detections'][0]['id'] for _ in range(2)]
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        statuses = list(pool.map(lambda record_id: client.post('/api/parking/events', json={
                            'record_id': record_id, 'plate': '51B12345', 'direction': 'in', 'confirmed': True}).status_code, arrivals))
                    self.assertEqual(sorted(statuses), [200, 409])
                    self.assertEqual(client.get('/api/parking').json()['inside'], 1)
            finally:
                module.DATA, module.API_KEY, module.app.state.engine = original_data, original_key, None


if __name__ == '__main__':
    unittest.main()
