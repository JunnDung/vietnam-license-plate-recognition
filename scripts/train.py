"""Fine-tune locally, then evaluate the best validation checkpoint on the untouched test set."""
import argparse
import csv
import hashlib
import json
import shutil
import time
from pathlib import Path

import torch
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=40)
    parser.add_argument('--batch', type=int, default=16)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--device', default='0' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    torch.set_num_threads(4)
    start = time.time()
    checkpoint = ROOT / 'runs/plate_detector/weights/last.pt'
    model = YOLO(str(checkpoint) if args.resume else 'yolo11n.pt')
    model.train(data=str(ROOT / 'data/plates/data.yaml'), epochs=args.epochs, batch=args.batch,
                imgsz=args.imgsz, device=args.device, workers=args.workers, seed=42, deterministic=True,
                project=str(ROOT / 'runs'), name='plate_detector', exist_ok=True,
                patience=10, fliplr=0, flipud=0, hsv_v=.55, degrees=8, translate=.1,
                scale=.35, mosaic=.5, close_mosaic=5, cache=False, resume=args.resume)
    trained = ROOT / 'runs/plate_detector/weights/best.pt'
    shutil.copy2(trained, ROOT / 'models/plate_detector.pt')
    metrics = YOLO(str(trained)).val(data=str(ROOT / 'data/plates/data.yaml'), split='test',
                                    imgsz=args.imgsz, batch=args.batch, device=args.device,
                                    workers=0, project=str(ROOT / 'runs'), name='test', exist_ok=True)
    with (ROOT / 'runs/plate_detector/results.csv').open(encoding='utf-8') as file:
        actual_epochs = len(list(csv.DictReader(file)))
    report = {'architecture': 'YOLO11n', 'base_checkpoint': 'yolo11n.pt', 'trained_locally': True,
              'gpu': torch.cuda.get_device_name(0) if args.device != 'cpu' else 'cpu',
              'requested_epochs': args.epochs, 'actual_epochs': actual_epochs, 'imgsz': args.imgsz, 'batch': args.batch,
              'elapsed_seconds': round(time.time()-start, 1), 'test': metrics.results_dict,
              'weights_sha256': hashlib.file_digest(trained.open('rb'), 'sha256').hexdigest()}
    (ROOT / 'reports/training.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    shutil.copy2(ROOT / 'runs/plate_detector/results.csv', ROOT / 'reports/training_curve.csv')
    for name in ('results.png', 'confusion_matrix_normalized.png'):
        if (ROOT / 'runs/plate_detector' / name).exists():
            shutil.copy2(ROOT / 'runs/plate_detector' / name, ROOT / 'reports' / name)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
