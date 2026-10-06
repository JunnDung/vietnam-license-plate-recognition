"""Fetch OCR once; inference uses local ONNX weights without a network connection."""
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://github.com/ankandrew/fast-plate-ocr/releases/download/arg-plates/'
FILES = {'cct_s_v2_global.onnx': ('plate_ocr.onnx', '384bbbd2cea3ef54761d3df70822ef3a349ee1a112aeafddbe0e3ba06bc6e47b'),
         'cct_s_v2_global_plate_config.yaml': ('plate_ocr_config.yaml', '0335c74a305173bb6f393efed0fde03cadeaa0b649ed8e19f431016d8232d0a6')}


def main():
    report = {'model': 'cct-s-v2-global-model', 'trained_in_this_project': False,
              'source': 'https://github.com/ankandrew/fast-plate-ocr', 'files': {}}
    for remote, (local, expected) in FILES.items():
        path = ROOT / 'models' / local
        if not path.exists():
            temporary = path.with_suffix('.download')
            urllib.request.urlretrieve(BASE + remote, temporary)
            with temporary.open('rb') as file:
                if hashlib.file_digest(file, 'sha256').hexdigest() != expected:
                    raise SystemExit(f'Checksum mismatch for {local}; download was not installed.')
            temporary.replace(path)
        with path.open('rb') as file:
            actual = hashlib.file_digest(file, 'sha256').hexdigest()
        if actual != expected:
            raise SystemExit(f'Checksum mismatch for existing {local}; move the file aside and rerun.')
        report['files'][local] = {'url': BASE + remote, 'sha256': actual}
    (ROOT / 'models/ocr_provenance.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
