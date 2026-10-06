"""Continue the detector on clean + corrupted TRAIN images; never publish weights automatically."""
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import yaml
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]


def augment(image, index):
    rng = np.random.default_rng(73 + index)
    kind = ('motion', 'motion', 'motion', 'night', 'rain')[index % 5]
    result = image.copy()
    if kind == 'motion':
        size = int(rng.choice([5, 7, 9, 11, 13]))
        kernel = np.zeros((size, size), np.float32)
        angle = float(rng.choice([0, 15, 30, 60, 90, 120, 150, 165]))
        center = (size - 1) / 2
        dx, dy = center * np.cos(np.deg2rad(angle)), center * np.sin(np.deg2rad(angle))
        cv2.line(kernel, (round(center-dx), round(center-dy)), (round(center+dx), round(center+dy)), 1, 1)
        kernel /= kernel.sum()
        result = cv2.filter2D(result, -1, kernel)
        if rng.random() < .25:
            result = np.clip((result.astype(np.float32)/255)**1.5 * 255 * .8, 0, 255).astype(np.uint8)
    elif kind == 'night':
        gamma, gain = float(rng.uniform(1.3, 2.4)), float(rng.uniform(.45, .85))
        result = (result.astype(np.float32)/255)**gamma * 255 * gain
        result += rng.normal(0, rng.uniform(1, 4), result.shape)
        result = np.clip(result, 0, 255).astype(np.uint8)
    else:
        fog = float(rng.uniform(.08, .3))
        result = (result.astype(np.float32)*(1-fog) + 180*fog).astype(np.uint8)
        overlay = result.copy()
        height, width = result.shape[:2]
        for _ in range(int(rng.integers(100, 350))):
            x, y = int(rng.integers(width)), int(rng.integers(height))
            cv2.line(overlay, (x, y), (x-4, y+int(rng.integers(8, 22))), (210, 210, 210), 1)
        result = cv2.addWeighted(result, .65, overlay, .35, 0)
    return result, kind


def prepare():
    source = ROOT / 'data/plates'
    target = ROOT / 'data/robust'
    for folder in ('images/train', 'labels/train'):
        (target / folder).mkdir(parents=True, exist_ok=True)
    images = sorted((source / 'images/train').glob('*'))
    if not images:
        raise ValueError('Prepare the original dataset first.')
    paths, records = [], []
    for index, path in enumerate(images):
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f'Cannot read {path}')
        transformed, kind = augment(image, index)
        destination = target / 'images/train' / (path.stem + '.jpg')
        if not cv2.imwrite(str(destination), transformed, [cv2.IMWRITE_JPEG_QUALITY, 92]):
            raise OSError(f'Cannot write {destination}')
        shutil.copy2(source / 'labels/train' / (path.stem+'.txt'), target / 'labels/train' / (path.stem+'.txt'))
        paths.extend([path.as_posix(), destination.as_posix()])
        records.append({'source': path.name, 'kind': kind, 'seed': 73+index})
    (target / 'train.txt').write_text('\n'.join(paths), encoding='utf-8')
    config = {'path': target.as_posix(), 'train': 'train.txt',
              'val': (source/'images/val').as_posix(), 'test': (source/'images/test').as_posix(),
              'names': {0: 'plate_long', 1: 'plate_square'}}
    (target / 'data.yaml').write_text(yaml.safe_dump(config), encoding='utf-8')
    manifest = {'seed': 73, 'clean_train': len(images), 'synthetic_train': len(records),
                'source_manifest_sha256': hashlib.sha256((ROOT/'reports/dataset.json').read_bytes()).hexdigest(),
                'geometry_unchanged': True, 'val_test_augmented_for_training': False, 'records': records}
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Prepared {len(paths)} training images, validation/test unchanged.', flush=True)
    return target, manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=18)
    parser.add_argument('--batch', type=int, default=16)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--device', default='0' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--weights', type=Path, default=ROOT/'models/plate_detector.pt')
    parser.add_argument('--name', default='plate_robust')
    args = parser.parse_args()
    if min(args.epochs, args.batch) < 1:
        parser.error('--epochs and --batch must be positive')
    if (ROOT/'runs'/args.name).exists():
        parser.error('Run already exists; use another --name to preserve previous checkpoints.')
    torch.set_num_threads(4)
    start = time.time()
    target, manifest = prepare()
    initial_hash = hashlib.sha256(args.weights.read_bytes()).hexdigest()
    model = YOLO(str(args.weights))
    model.train(data=str(target/'data.yaml'), epochs=args.epochs, batch=args.batch, imgsz=640,
                device=args.device, workers=args.workers, seed=73, deterministic=True,
                project=str(ROOT/'runs'), name=args.name, exist_ok=False, patience=6,
                optimizer='AdamW', lr0=.0003, lrf=.1, warmup_epochs=1,
                fliplr=0, flipud=0, hsv_v=.25, degrees=5, translate=.05,
                scale=.2, mosaic=.2, close_mosaic=4, cache=False)
    report = {'base_weights_sha256': initial_hash, 'run': args.name, 'requested_epochs': args.epochs,
              'clean_train': manifest['clean_train'], 'synthetic_train': manifest['synthetic_train'],
              'augmentation_manifest_sha256': hashlib.sha256((target/'manifest.json').read_bytes()).hexdigest(),
              'elapsed_seconds': round(time.time()-start, 1),
              'selection': 'Candidate best/last must pass paired validation before deployment; test is not used to select.'}
    (ROOT/'runs'/args.name/'hardening_training.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
