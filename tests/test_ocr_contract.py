"""The model consumes RGB; probabilities refer to raw character slots."""
import unittest
from types import SimpleNamespace
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np
import cv2

from recognition import PlateEngine, rectify_plate


class OCRContracts(unittest.TestCase):
    def test_model_endpoint_exposes_benchmark_summary_without_predictions(self):
        import app
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'reports').mkdir()
            report={'results':{'baseline':{'correct':9,'predictions':[{'expected':'51A12345'}]},
                               'candidate':{'correct':10,'predictions':[{'expected':'51A12345'}]}}}
            (root/'reports/ocr_benchmark.json').write_text(json.dumps(report),encoding='utf-8')
            with patch.object(app,'ROOT',root):result=app.model_report()['ocr_benchmark']
            self.assertEqual(result['results']['candidate']['correct'],10)
            for item in result['results'].values():self.assertNotIn('predictions',item)

    def test_rectification_uses_large_bright_plate_border_only(self):
        crop=np.zeros((140,220,3),np.uint8)
        corners=np.array([[35,10],[210,40],[185,130],[10,100]],np.int32)
        cv2.fillConvexPoly(crop,corners,(230,230,230))
        cv2.putText(crop,'51A',(45,65),cv2.FONT_HERSHEY_SIMPLEX,.8,(0,0,0),2)
        corrected=rectify_plate(crop)
        self.assertIsNotNone(corrected)
        self.assertGreater(corrected.shape[1],corrected.shape[0])
        self.assertGreater(corrected[:4,4:-4].mean(),200)
        self.assertIsNone(rectify_plate(np.full((40,100,3),180,np.uint8)))
        self.assertIsNone(rectify_plate(np.zeros((40,100,3),np.uint8)))
        small=np.zeros((140,220,3),np.uint8)
        cv2.fillConvexPoly(small,corners//3,(230,230,230))
        self.assertIsNone(rectify_plate(small))

    def test_rgb_for_every_variant_without_mutating_bgr(self):
        crop=np.full((40,100,3),(10,20,200),dtype=np.uint8)
        original=crop.copy()
        received=[]
        def run(images,**kwargs):
            received.extend(images)
            return [SimpleNamespace(plate='51A12345',char_probs=np.full(10,.9)) for _ in images]
        engine=object.__new__(PlateEngine)
        engine.ocr=SimpleNamespace(run=run)
        engine.read_crop(crop,square=True)
        self.assertEqual(len(received),3)
        np.testing.assert_array_equal(received[0][0,0],[200,20,10])
        for image in received:
            self.assertGreater(image[:,:,0].mean(),image[:,:,2].mean())
        np.testing.assert_array_equal(crop,original)

    def test_confidence_excludes_padding_and_punctuation_at_original_slots(self):
        engine=object.__new__(PlateEngine)
        for raw,probs,expected in [('51A_12345',[.9,.9,.9,.01,.8,.8,.8,.8,.8,.01],.8375),
                                   ('51A-123.45',[.9,.9,.9,.01,.8,.8,.8,.01,.8,.8],.8375),
                                   ('__________',[.99]*10,0.)]:
            with self.subTest(raw=raw):
                engine.ocr=SimpleNamespace(run=lambda *a,**kw:[SimpleNamespace(plate=raw,char_probs=probs)])
                reading=engine.read_crop(np.full((40,160,3),180,np.uint8))
                self.assertAlmostEqual(reading['ocr_confidence'],expected)
                self.assertEqual(reading['plate'],'' if raw.startswith('_') else '51A12345')


if __name__=='__main__':unittest.main()
