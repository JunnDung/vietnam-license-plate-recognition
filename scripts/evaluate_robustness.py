"""Paired detector stress test. Synthetic corruption is not real-weather validation."""
import argparse
import hashlib
import json
import random
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]


def corrupt(image, condition, seed):
    if condition == 'original':
        return image
    if condition == 'synthetic_dark':
        return np.clip((image.astype(np.float32) / 255) ** 1.9 * 255 * .65, 0, 255).astype(np.uint8)
    if condition == 'synthetic_motion_blur':
        kernel = np.zeros((11, 11), dtype=np.float32)
        kernel[5, :] = 1 / 11
        return cv2.filter2D(image, -1, kernel)
    if condition == 'synthetic_rain_fog':
        result = image.astype(np.float32) * .75 + 180 * .25
        result = result.astype(np.uint8)
        rng = np.random.default_rng(seed)
        height, width = image.shape[:2]
        overlay = result.copy()
        for _ in range(250):
            x, y = int(rng.integers(0, width)), int(rng.integers(0, height))
            cv2.line(overlay, (x, y), (x-4, y+15), (210, 210, 210), 1)
        return cv2.addWeighted(result, .65, overlay, .35, 0)
    raise ValueError(condition)


def iou(a, b):
    intersection = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection
    return intersection / union if union > 0 else 0.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--samples', type=int, default=200)
    parser.add_argument('--device', default='0' if torch.cuda.is_available() else 'cpu')
    args = parser.parse_args()
    torch.set_num_threads(4)
    images = sorted((ROOT / 'data/plates/images/test').glob('*'))
    random.Random(42).shuffle(images)
    images = images[:args.samples]
    model = YOLO(str(ROOT / 'models/plate_detector.pt'))
    with (ROOT / 'models/plate_detector.pt').open('rb') as file:
        weights_hash = hashlib.file_digest(file, 'sha256').hexdigest()
    report = {'weights_sha256': weights_hash, 'kind': 'paired synthetic detector stress test', 'seed': 42, 'confidence': .35, 'iou_threshold': .5,
              'limitations': 'Synthetic brightness, blur, rain and fog on a subset of test images. Not actual day/night/weather labels. Not OCR accuracy.',
              'sample_list_sha256': hashlib.sha256('\n'.join(p.name for p in images).encode()).hexdigest(), 'conditions': {}}
    for condition in ('original', 'synthetic_dark', 'synthetic_rain_fog', 'synthetic_motion_blur'):
        matched, truth_count, prediction_count = 0, 0, 0
        for start in range(0, len(images), 8):
            paths = images[start:start+8]
            frames = [cv2.imread(str(path)) for path in paths]
            results = model.predict([corrupt(frame, condition, start+offset) for offset, frame in enumerate(frames)],
                                    conf=.35, imgsz=640, device=args.device, verbose=False)
            for path, frame, result in zip(paths, frames, results):
                height, width = frame.shape[:2]
                truth = []
                for line in (ROOT / 'data/plates/labels/test' / (path.stem + '.txt')).read_text().splitlines():
                    label, x, y, w, h = map(float, line.split())
                    truth.append((int(label), [(x-w/2)*width, (y-h/2)*height, (x+w/2)*width, (y+h/2)*height]))
                available = set(range(len(truth)))
                for box in sorted(result.boxes, key=lambda box: float(box.conf.item()), reverse=True):
                    coordinates = box.xyxy[0].cpu().tolist()
                    candidates = [(iou(coordinates, truth[index][1]), index) for index in available
                                  if int(box.cls.item()) == truth[index][0]]
                    if candidates:
                        overlap, index = max(candidates)
                        if overlap >= .5:
                            matched += 1
                            available.remove(index)
                truth_count += len(truth)
                prediction_count += len(result.boxes)
        report['conditions'][condition] = {'images': len(images), 'ground_truth_plates': truth_count,
                                            'predictions': prediction_count, 'matched': matched,
                                            'recall_at_iou50': matched / truth_count if truth_count else 0,
                                            'precision_at_iou50': matched / prediction_count if prediction_count else 0}
        print(condition, report['conditions'][condition], flush=True)
    (ROOT / 'reports/robustness.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
