"""Score manually transcribed held-out plates: OCR on labeled crops and full pipeline."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import cv2
import torch
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recognition import PlateEngine
from scripts.evaluate_robustness import corrupt, iou


def distance(a, b):
    previous = list(range(len(b)+1))
    for index, char in enumerate(a, 1):
        current = [index]
        for other_index, other in enumerate(b, 1):
            current.append(min(current[-1]+1, previous[other_index]+1,
                               previous[other_index-1]+(char != other)))
        previous = current
    return previous[-1]


def score(engine, labels, condition):
    results, exact, full_exact, errors, characters, latencies = [], 0, 0, 0, 0, []
    for sample in labels['samples']:
        image = cv2.imread(str(ROOT / 'data/plates' / sample['image']))
        image = corrupt(image, condition, sample['index'])
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
    return {'condition': condition, 'samples': len(results), 'selected_before_predictions': labels['selected_before_predictions'],
              'annotation_audit': labels.get('audit_note'),
              'exact_match': exact / len(results), 'pipeline_exact_match': full_exact / len(results),
              'character_error_rate': errors / characters,
              'mean_ms_crop_plus_pipeline': sum(latencies) / len(latencies), 'device': engine.device,
              'limitations': 'Small manually transcribed, readable subset of test data. Unreadable exclusions recorded. Not population accuracy or real-weather evaluation.',
              'excluded': labels['excluded'], 'results': results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--weights', type=Path, default=ROOT / 'models/plate_detector.pt')
    parser.add_argument('--weather', action='store_true', help='Also score corrupted versions; keep all 37 readable-source samples')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    torch.set_num_threads(2)
    engine = PlateEngine(detector=YOLO(str(args.weights)), device=args.device)
    labels = json.loads((ROOT / 'reports/ocr_ground_truth.json').read_text(encoding='utf-8'))
    conditions = ('original', 'synthetic_dark', 'synthetic_rain_fog', 'synthetic_motion_blur') if args.weather else ('original',)
    evaluations = {}
    for condition in conditions:
        evaluations[condition] = score(engine, labels, condition)
        print(json.dumps({key: value for key, value in evaluations[condition].items() if key not in ('results', 'excluded')}, indent=2), flush=True)
    report = evaluations['original']
    report['weights_sha256'] = hashlib.sha256(args.weights.read_bytes()).hexdigest()
    if args.weather:
        report = {'weights_sha256': report['weights_sha256'], 'kind': 'paired synthetic OCR and pipeline stress test',
                  'ground_truth_sha256': hashlib.sha256((ROOT/'reports/ocr_ground_truth.json').read_bytes()).hexdigest(),
                  'limitations': '37 small readable-source samples with assistant annotations; no additional exclusions under corruption. Not real-weather validation.',
                  'conditions': evaluations}
    output = args.output or ROOT / 'reports' / ('ocr_weather.json' if args.weather else 'ocr_evaluation.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
