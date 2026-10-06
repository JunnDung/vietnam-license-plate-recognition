"""Score manually transcribed held-out plates: OCR on labeled crops and full pipeline."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import cv2
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recognition import PlateEngine
from scripts.evaluate_robustness import iou


def distance(a, b):
    previous = list(range(len(b)+1))
    for index, char in enumerate(a, 1):
        current = [index]
        for other_index, other in enumerate(b, 1):
            current.append(min(current[-1]+1, previous[other_index]+1,
                               previous[other_index-1]+(char != other)))
        previous = current
    return previous[-1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default='cpu')
    args = parser.parse_args()
    torch.set_num_threads(2)
    engine = PlateEngine(device=args.device)
    labels = json.loads((ROOT / 'reports/ocr_ground_truth.json').read_text(encoding='utf-8'))
    results, exact, full_exact, errors, characters, latencies = [], 0, 0, 0, 0, []
    for sample in labels['samples']:
        image = cv2.imread(str(ROOT / 'data/plates' / sample['image']))
        x0, y0, x1, y1 = sample['bbox']
        start = time.perf_counter()
        with engine.lock:
            reading = engine.read_crop(image[y0:y1, x0:x1], square=sample['layout']==1)
        detections = engine.predict(image)
        latencies.append((time.perf_counter()-start)*1000)
        candidates = [item for item in detections if iou(item['bbox'], sample['bbox']) >= .5]
        predicted = max(candidates, key=lambda item: item['detector_confidence'])['plate'] if candidates else ''
        expected = sample['expected']
        exact += reading['plate'] == expected
        full_exact += predicted == expected
        errors += distance(expected, reading['plate'])
        characters += len(expected)
        results.append({'index': sample['index'], 'expected': expected, 'crop_ocr': reading['plate'],
                        'pipeline': predicted, 'ocr_confidence': reading['ocr_confidence']})
    with (ROOT / 'models/plate_detector.pt').open('rb') as file:
        weights_hash = hashlib.file_digest(file, 'sha256').hexdigest()
    report = {'weights_sha256': weights_hash, 'samples': len(results), 'selected_before_predictions': labels['selected_before_predictions'],
              'annotation_audit': labels.get('audit_note'),
              'exact_match': exact / len(results), 'pipeline_exact_match': full_exact / len(results),
              'character_error_rate': errors / characters,
              'mean_ms_crop_plus_pipeline': sum(latencies) / len(latencies), 'device': args.device,
              'limitations': 'Small manually transcribed, readable subset of test data. Unreadable exclusions recorded. Not population accuracy or real-weather evaluation.',
              'excluded': labels['excluded'], 'results': results}
    (ROOT / 'reports/ocr_evaluation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'results'}, indent=2))


if __name__ == '__main__':
    main()
