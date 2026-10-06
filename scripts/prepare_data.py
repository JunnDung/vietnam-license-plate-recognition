"""Download, validate and group-split Vietnamese polygon annotations for YOLO detection."""
import argparse
import hashlib
import io
import json
import random
import re
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'b8a1e809cadea0e53b1c519f637d494f0d87796f'
URL = f'https://huggingface.co/datasets/hoanglvuit/Vietnam_License_Plate_Segment_Datasets/resolve/{REVISION}/dataset.zip'
ARCHIVE_SHA256 = '0bda89d129502a4c0f05e7b693b639f655b7eda0a85d2ee6639a0227fd968865'


def polygon_to_box(line):
    values = [float(v) for v in line.split()]
    label, coordinates = int(values[0]), values[1:]
    if values[0] != label or label not in (0, 1):
        raise ValueError('Invalid class')
    if len(coordinates) < 6 or len(coordinates) % 2:
        raise ValueError('Expected normalized polygon')
    if not all(np.isfinite(v) and 0 <= v <= 1 for v in coordinates):
        raise ValueError('Invalid coordinates')
    xs, ys = coordinates[::2], coordinates[1::2]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    if x1 <= x0 or y1 <= y0:
        raise ValueError('Empty polygon')
    return f'{label} {(x0+x1)/2:.8f} {(y0+y1)/2:.8f} {x1-x0:.8f} {y1-y0:.8f}'


def capture_group(stem):
    # ponytail: sequence blocks approximate capture groups; use camera/vehicle IDs when provided.
    match = re.match(r'^(.*?)(\d+)$', stem)
    return f'{match[1]}:{int(match[2]) // 25}' if match else re.split(r'_jpg|_png|\.rf\.', stem)[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, default=ROOT / 'data/raw/dataset.zip')
    args = parser.parse_args()
    archive = args.archive
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        temporary = archive.with_suffix('.download')
        urllib.request.urlretrieve(URL, temporary)
        temporary.replace(archive)
    with archive.open('rb') as file:
        archive_hash = hashlib.file_digest(file, 'sha256').hexdigest()
    if archive_hash != ARCHIVE_SHA256:
        raise SystemExit('Dataset archive checksum mismatch. No split was written.')
    output = ROOT / 'data/plates'
    if output.exists():
        raise SystemExit('data/plates already exists; keep the existing split or move it before rebuilding.')
    groups, seen, rejected, duplicates = defaultdict(list), set(), [], 0
    with zipfile.ZipFile(archive) as z:
        names = set(z.namelist())
        for name in sorted(names):
            path = Path(name)
            if not name.startswith('images/') or path.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
                continue
            label_name = name.replace('images/', 'labels/', 1).rsplit('.', 1)[0] + '.txt'
            try:
                raw = z.read(name)
                with Image.open(io.BytesIO(raw)) as im:
                    im.load()
                    if min(im.size) < 20 or im.width * im.height > 20_000_000:
                        raise ValueError('Invalid image size')
                    digest = hashlib.sha256(im.convert('RGB').tobytes()).hexdigest()
                if digest in seen:
                    duplicates += 1
                    continue
                if label_name not in names:
                    raise ValueError('Missing label')
                lines = z.read(label_name).decode().splitlines()
                converted = '\n'.join(polygon_to_box(line) for line in lines if line.strip())
                if not converted:
                    raise ValueError('Empty label')
                seen.add(digest)
                groups[capture_group(path.stem)].append((name, converted, digest))
            except (ValueError, OSError, KeyError) as error:
                rejected.append({'image': name, 'reason': str(error)})
        group_names = sorted(groups)
        random.Random(42).shuffle(group_names)
        total, cumulative = len(seen), 0
        counts, manifest = defaultdict(int), []
        for group in group_names:
            fraction = cumulative / total
            split = 'train' if fraction < .7 else 'val' if fraction < .85 else 'test'
            for name, label, digest in groups[group]:
                filename = digest[:16] + Path(name).suffix.lower()
                dest = output / 'images' / split / filename
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(name))
                target = output / 'labels' / split / (dest.stem + '.txt')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(label + '\n')
                manifest.append({'source': name, 'image': str(dest.relative_to(output)).replace('\\', '/'),
                                 'sha256_pixels': digest, 'group': group, 'split': split})
                counts[split] += 1
            cumulative += len(groups[group])
    (output / 'data.yaml').write_text(
        f'path: {output.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\n'
        'names:\n  0: plate_long\n  1: plate_square\n', encoding='utf-8')
    report = {'source_url': URL, 'revision': REVISION, 'archive_sha256': archive_hash,
              'seed': 42, 'split_method': 'capture prefix + sequence blocks of 25; exact pixel deduplication',
              'limitations': 'No vehicle/camera IDs; different views of the same plate may still cross splits. No weather labels or OCR transcriptions.',
              'counts': dict(counts), 'groups': len(groups), 'duplicates_removed': duplicates,
              'rejected': rejected, 'samples': manifest}
    (ROOT / 'reports/dataset.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'samples'}, indent=2))


if __name__ == '__main__':
    main()
