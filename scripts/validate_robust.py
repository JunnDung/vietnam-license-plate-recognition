"""Select on paired validation, measure test once, then deploy the accepted candidate."""
import argparse
import csv
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recognition import PlateEngine
from scripts.evaluate_ocr import score
from scripts.evaluate_robustness import evaluate


def clean_metrics(weights, split, device, name):
    return YOLO(str(weights)).val(data=str(ROOT/'data/plates/data.yaml'), split=split,
                                  imgsz=640, batch=16, device=device, workers=0,
                                  project=str(ROOT/'runs'), name=name, exist_ok=True).results_dict


def passes(baseline, candidate):
    base, current = baseline['robustness']['conditions'], candidate['robustness']['conditions']
    return (candidate['clean']['metrics/mAP50-95(B)'] >= baseline['clean']['metrics/mAP50-95(B)'] - .015
            and current['synthetic_motion_blur']['recall_at_iou50'] >= base['synthetic_motion_blur']['recall_at_iou50'] + .03
            and all(item['recall_at_iou50'] >= base[name]['recall_at_iou50'] - .01
                    and item['precision_at_iou50'] >= .95 for name, item in current.items()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--baseline-report-dir', type=Path, default=ROOT/'reports')
    parser.add_argument('--baseline-ocr-weather', type=Path, help='Optional paired OCR baseline from evaluate_ocr.py --weather')
    parser.add_argument('--run', default='plate_robust')
    parser.add_argument('--device', default='0')
    args = parser.parse_args()
    run = ROOT/'runs'/args.run
    if not (run/'hardening_training.json').exists():
        parser.error('Training must finish before validation and deployment.')
    original = {name: json.loads((args.baseline_report_dir/f'{name}.json').read_text(encoding='utf-8'))
                for name in ('training', 'robustness', 'ocr_evaluation')}
    base_hash = hashlib.sha256(args.baseline.read_bytes()).hexdigest()
    if original['training']['weights_sha256'] != base_hash:
        parser.error('Baseline weights do not match the supplied training report.')
    report = {'created_at': datetime.now(timezone.utc).isoformat(),
              'selection_rule': 'Validation only: motion recall gain >= 3 percentage points; clean mAP50-95 drop <= 1.5 points; recall drop <= 1 point per condition; precision >= 95% per condition.',
              'validation_samples': 200, 'baseline': {'weights_sha256': base_hash, 'training': original['training'],
                                                     'test': {'robustness': original['robustness'], 'ocr_evaluation': original['ocr_evaluation']}},
              'training': json.loads((run/'hardening_training.json').read_text()), 'candidates': {},
              'test_reuse_note': 'The previous test results informed the diagnosis of v1 motion weakness. This reused test is a regression benchmark, not a never-observed independent holdout. Checkpoint selection in this run uses validation only.',
              'limitations': 'Synthetic corruptions and a small OCR subset, no physical night/rain camera or camera-independent split.'}
    if args.baseline_ocr_weather:
        baseline_ocr = json.loads(args.baseline_ocr_weather.read_text(encoding='utf-8'))
        truth_hash = hashlib.sha256((ROOT/'reports/ocr_ground_truth.json').read_bytes()).hexdigest()
        if baseline_ocr['weights_sha256'] != base_hash or baseline_ocr['ground_truth_sha256'] != truth_hash:
            parser.error('OCR baseline weights/annotations do not match this comparison.')
        report['baseline']['test']['ocr_weather'] = baseline_ocr
    base_val = {'clean': clean_metrics(args.baseline, 'val', args.device, 'robust_baseline_val'),
                'robustness': evaluate(args.baseline, 'val', 200, args.device)}
    report['baseline']['validation'] = base_val
    for name in ('best', 'last'):
        weights = run/'weights'/f'{name}.pt'
        candidate = {'clean': clean_metrics(weights, 'val', args.device, f'robust_{name}_val'),
                     'robustness': evaluate(weights, 'val', 200, args.device)}
        candidate['passed'] = passes(base_val, candidate)
        report['candidates'][name] = candidate
        print(f'Validation {name}: passed={candidate["passed"]}', flush=True)
    accepted = [name for name, result in report['candidates'].items() if result['passed']]
    if not accepted:
        report['deployed_candidate'] = None
        (ROOT/'reports/hardening.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        raise SystemExit('No candidate passed validation; current model preserved.')
    chosen = max(accepted, key=lambda name: report['candidates'][name]['robustness']['conditions']['synthetic_motion_blur']['recall_at_iou50'])
    weights = run/'weights'/f'{chosen}.pt'
    report['selected_candidate'] = chosen
    report['deployed_candidate'] = None
    report['selected_before_test'] = True
    report['selection_weights_sha256'] = hashlib.sha256(weights.read_bytes()).hexdigest()
    # Freeze the decision before test; test measurements never choose between best and last.
    (ROOT/'reports/hardening.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    test = clean_metrics(weights, 'test', args.device, 'robust_test')
    stress = evaluate(weights, 'test', 200, args.device)
    labels = json.loads((ROOT/'reports/ocr_ground_truth.json').read_text(encoding='utf-8'))
    engine = PlateEngine(detector=YOLO(str(weights)), device='cpu')
    weather = {condition: score(engine, labels, condition) for condition in stress['conditions']}
    weights_hash = hashlib.sha256(weights.read_bytes()).hexdigest()
    if weights_hash != report['selection_weights_sha256']:
        raise RuntimeError('Candidate changed after validation; current model preserved.')
    ocr = {**weather['original'], 'weights_sha256': weights_hash}
    ocr_weather = {'weights_sha256': weights_hash, 'kind': 'paired synthetic OCR and pipeline stress test',
                   'ground_truth_sha256': hashlib.sha256((ROOT/'reports/ocr_ground_truth.json').read_bytes()).hexdigest(),
                   'conditions': weather, 'limitations': report['limitations']}
    curve = list(csv.DictReader((run/'results.csv').open(encoding='utf-8')))
    training = {**original['training'], 'base_checkpoint': f'detector sha256:{base_hash}',
                'base_weights_sha256': base_hash, 'requested_epochs': report['training']['requested_epochs'],
                'actual_epochs': len(curve), 'elapsed_seconds': report['training']['elapsed_seconds'],
                'weights_sha256': weights_hash, 'test': test, 'stage': 'robustness fine-tune',
                'base_training_epochs': original['training']['actual_epochs'],
                'clean_train': report['training']['clean_train'], 'synthetic_train': report['training']['synthetic_train'],
                'selected_checkpoint': chosen, 'hyperparameters': yaml.safe_load((run/'args.yaml').read_text())}
    report['test'] = {'clean': test, 'robustness': stress}
    report['deployed_candidate'] = chosen
    report['deployed_weights_sha256'] = weights_hash
    for name, result in (('training', training), ('robustness', stress), ('ocr_evaluation', ocr), ('ocr_weather', ocr_weather), ('hardening', report)):
        (ROOT/'reports'/f'{name}.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    shutil.copy2(run/'results.csv', ROOT/'reports/training_curve.csv')
    shutil.copy2(run/'results.png', ROOT/'reports/results.png')
    shutil.copy2(ROOT/'runs/robust_test/confusion_matrix_normalized.png', ROOT/'reports/confusion_matrix_normalized.png')
    temporary = ROOT/'models/plate_detector.new.pt'
    shutil.copy2(weights, temporary)
    temporary.replace(ROOT/'models/plate_detector.pt')
    print(f'Deployed {chosen}; SHA-256 {weights_hash}. Restart API to load it.', flush=True)


if __name__ == '__main__':
    main()
