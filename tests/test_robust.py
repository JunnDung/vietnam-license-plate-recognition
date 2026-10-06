"""Check corruptions preserve coordinates and burst capture keeps the sharp frame."""
import unittest
import threading
from types import SimpleNamespace
from copy import deepcopy

import cv2
import numpy as np
import torch

from scripts.camera import best_frame, sharpness
from scripts.train_robust import augment
from scripts.validate_robust import passes
from scripts.evaluate_robustness import corrupt
from recognition import PlateEngine, crop_quality


class RobustChecks(unittest.TestCase):
    def test_corruption_and_burst(self):
        image = np.full((240, 320, 3), 180, np.uint8)
        cv2.putText(image, '51A 12345', (15, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (10, 10, 10), 3)
        for index, kind in enumerate(('motion', 'motion', 'motion', 'night', 'rain')):
            changed, actual_kind = augment(image, index)
            self.assertEqual(actual_kind, kind)
            self.assertEqual(changed.shape, image.shape)
            self.assertEqual(changed.dtype, image.dtype)
            self.assertFalse(np.array_equal(changed, image))
            self.assertTrue(np.array_equal(changed, augment(image, index)[0]))
        blurred = cv2.GaussianBlur(image, (15, 15), 4)
        self.assertGreater(sharpness(image), sharpness(blurred))

        class Capture:
            def __init__(self): self.frames = [image, blurred]; self.time = 0.
            def read(self):
                if not self.frames: return False, None
                self.time += .1
                return True, self.frames.pop(0)
            def get(self, key): return self.time * 1000

        selected, score, count, timestamp = best_frame(Capture(), blurred, 3)
        self.assertTrue(np.array_equal(selected, image))
        self.assertEqual(count, 3)
        self.assertAlmostEqual(timestamp, .1)
        self.assertEqual(score, sharpness(image))
        for name in ('synthetic_night_noise', 'synthetic_diagonal_blur', 'synthetic_rain_blur'):
            result = corrupt(image, name, 42)
            self.assertEqual(result.shape, image.shape)
            self.assertTrue(np.array_equal(result, corrupt(image, name, 42)))
        self.assertIn('low_light', crop_quality(np.zeros((60, 120, 3), np.uint8))['issues'])
        self.assertIn('low_detail', crop_quality(np.full((60, 120, 3), 180, np.uint8))['issues'])
        self.assertIn('small_plate', crop_quality(np.full((12, 24, 3), 180, np.uint8))['issues'])

    def test_high_ocr_confidence_still_reviews_low_detail(self):
        box = SimpleNamespace(xyxy=torch.tensor([[10., 10., 120., 70.]]), cls=torch.tensor(0), conf=torch.tensor(.99))
        detector = SimpleNamespace(predict=lambda *args, **kwargs: [SimpleNamespace(boxes=[box])])
        engine = object.__new__(PlateEngine)
        engine.detector, engine.device, engine.lock = detector, 'cpu', threading.Lock()
        engine.min_detail, engine.min_brightness = 25., 40.
        engine.read_crop = lambda *args, **kwargs: {'plate': '51A12345', 'raw_text': '51A12345', 'ocr_confidence': .99, 'valid_format': True}
        item = engine.predict(np.full((100, 160, 3), 180, np.uint8))[0]
        self.assertTrue(item['needs_review'])
        self.assertEqual(item['quality']['issues'], ['low_detail'])

    def test_conflicting_valid_ocr_is_reported(self):
        engine = object.__new__(PlateEngine)
        predictions = [SimpleNamespace(plate=text, char_probs=np.full(8, probability))
                       for text, probability in [('51A12345', .99), ('51A12346', .95)]]
        engine.ocr = SimpleNamespace(run=lambda *args, **kwargs: predictions)
        reading = engine.read_crop(np.full((40, 160, 3), 180, np.uint8))
        self.assertEqual(reading['plate'], '51A12345')
        self.assertTrue(reading['ocr_disagreement'])

    def test_candidate_requires_gain_without_regression(self):
        base = {'clean': {'metrics/mAP50-95(B)': .9}, 'robustness': {'conditions': {
            name: {'recall_at_iou50': recall, 'precision_at_iou50': .98}
            for name, recall in [('original', .98), ('synthetic_dark', .98), ('synthetic_rain_fog', .98), ('synthetic_motion_blur', .8)]}}}
        candidate = deepcopy(base)
        candidate['robustness']['conditions']['synthetic_motion_blur']['recall_at_iou50'] = .9
        self.assertTrue(passes(base, candidate))
        candidate['clean']['metrics/mAP50-95(B)'] = .87
        self.assertFalse(passes(base, candidate))
        candidate['clean']['metrics/mAP50-95(B)'] = .9
        candidate['robustness']['conditions']['synthetic_dark']['precision_at_iou50'] = .94
        self.assertFalse(passes(base, candidate))


if __name__ == '__main__':
    unittest.main()
