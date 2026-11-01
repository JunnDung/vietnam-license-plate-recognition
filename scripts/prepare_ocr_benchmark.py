"""Prepare a plate-identity-disjoint VNLP evaluation from the original labeled archive."""
import argparse
from collections import defaultdict
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://github.com/fict-labs/VNLP/tree/d0b38df15c961393a7a1189912476c3d8d1edbfc'
URL = 'https://drive.usercontent.google.com/download?id=1sNmk3U15qkw2xIJ58BmvDrbqLohBmZZY&export=download&confirm=t'
SEED = 'vnlp-20261102'
ARCHIVE_SHA256 = 'f9da66c4cb443375ff40be140628ccfb3dc35f22755d82e341299e05b07a4a21'


def parse_name(member):
    path = PurePosixPath(member)
    if path.is_absolute() or '..' in path.parts or len(path.parts) != 3 or path.parts[0] != 'detection':
        raise ValueError('Invalid source path')
    match = re.fullmatch(r'\d+_\d+_\d+_([A-Za-z0-9]{6,10})_(\d+)_(\d+)_(\d+)_(\d+)\.jpg',path.name)
    if not match:
        raise ValueError('Unrecognized VNLP label filename')
    x0,y0,x1,y1 = map(int,match.groups()[1:])
    if x1 <= x0 or y1 <= y0:
        raise ValueError('Invalid label box')
    return {'member':member,'plate':match[1].upper(),'bbox':[x0,y0,x1,y1],
            'square':path.parts[1].startswith('two_row')}


def rank(text):
    return hashlib.sha256((SEED+':'+text.upper()).encode()).hexdigest()


def partition(plate):
    return 'dev' if int(rank(plate)[:8],16)%5 == 0 else 'test'


def deduplicate(rows):
    pixels = defaultdict(list)
    for row in rows:
        pixels[row['pixel_sha256']].append(row)
    kept, duplicate, conflict = [],0,0
    for group in pixels.values():
        if len({row['plate'] for row in group})>1:
            conflict+=len(group)
        else:
            kept.append(min(group,key=lambda row:row['member']))
            duplicate+=len(group)-1
    return kept, {'duplicate_images':duplicate,'conflicting_images':conflict}


def main():
    from PIL import Image
    parser=argparse.ArgumentParser()
    parser.add_argument('--archive',type=Path,default=ROOT/'data/raw/VNLP_detection.zip')
    parser.add_argument('--limit',type=int,default=2000,help='Predeclared identity sample cap, selected before inference')
    parser.add_argument('--manifest',type=Path,default=ROOT/'reports/ocr_benchmark_manifest.json')
    args=parser.parse_args()
    if args.limit<2:parser.error('--limit must be at least 2')
    if args.manifest.exists():parser.error('Manifest already frozen; use a new output path to rebuild.')
    folder=ROOT/'data/ocr_benchmark';folder.mkdir(parents=True,exist_ok=True)
    with args.archive.open('rb') as file:
        archive_hash=hashlib.file_digest(file,'sha256').hexdigest()
    if archive_hash != ARCHIVE_SHA256:raise ValueError('Source archive checksum mismatch')
    legacy=json.loads((ROOT/'reports/ocr_ground_truth.json').read_text(encoding='utf-8'))
    excluded={row['expected'] for row in legacy['samples'] if row.get('expected')}
    rows,rejected=[],[]
    with zipfile.ZipFile(args.archive) as archive:
        names=sorted(name for name in archive.namelist() if name.lower().endswith('.jpg'))
        for index,name in enumerate(names):
            try:
                row=parse_name(name)
                with Image.open(io.BytesIO(archive.read(name))) as source:
                    source=source.convert('RGB');x0,y0,x1,y1=row['bbox']
                    if x1>source.width or y1>source.height:raise ValueError('Label extends beyond source image')
                    crop=source.crop(row['bbox'])
                    row['pixel_sha256']=hashlib.sha256(str(crop.size).encode()+crop.tobytes()).hexdigest()
                    row['source_pixel_sha256']=hashlib.sha256(str(source.size).encode()+source.tobytes()).hexdigest()
                    row['size']=list(crop.size)
                    rows.append(row)
            except (ValueError,OSError,KeyError) as error:
                rejected.append({'member':name,'reason':str(error)})
            if (index+1)%5000==0:print(f'Audited {index+1}/{len(names)} images',flush=True)
        unique,audit=deduplicate(rows)
        identities=defaultdict(list)
        for row in unique:
            if row['plate'] not in excluded:identities[row['plate']].append(row)
        selected=[min(identities[plate],key=lambda row:rank(row['member'])) for plate in sorted(identities,key=rank)[:args.limit]]
        for row in selected:
            identity=hashlib.sha256(row['member'].encode()).hexdigest()[:24]
            row.update(split=partition(row['plate']),image=f'data/ocr_benchmark/{identity}.png',source_image=f'data/ocr_benchmark/{identity}-source.jpg')
            raw=archive.read(row['member'])
            (ROOT/row['source_image']).write_bytes(raw)
            row['source_sha256']=hashlib.sha256(raw).hexdigest()
            with Image.open(io.BytesIO(raw)) as image:
                image.convert('RGB').crop(row['bbox']).save(ROOT/row['image'])
            row['image_sha256']=hashlib.sha256((ROOT/row['image']).read_bytes()).hexdigest()
    dev={row['plate'] for row in selected if row['split']=='dev'}
    test={row['plate'] for row in selected if row['split']=='test'}
    assert dev and test and not dev&test
    report={'source':SOURCE,'download_url':URL,'archive_sha256':archive_hash,
            'license':'Authors offer a free download and request citation; no explicit redistribution license found. Images remain local.',
            'protocol':'One sample per plate identity; rank identities and source members by SHA256(seed:text), cap fixed before inference. Pixel duplicates removed and conflicting pixel labels excluded. Split identity hash modulo 5: 0 dev, remainder test.',
            'seed':SEED,'identity_cap':args.limit,'source_images':len(names),'eligible_unique_pixels':len(unique),
            'excluded_legacy_plate_identities':sorted(excluded),
            'bbox_convention':'Filename final four integers interpreted as x0,y0,x1,y1. Archive readme says width-height, but these are opposite corners, verified on decoded crops before inference.',
            'source_identities':len(identities),'audit':audit,'rejected':rejected,'counts':{'dev':len(dev),'test':len(test)},
            'limitations':'Public OCR pretrained training overlap unknown. Test is unseen by this change, not proven unseen by upstream pretraining. Filename annotations were not independently human audited. Crop-only results do not measure detection.',
            'samples':selected}
    args.manifest.parent.mkdir(parents=True,exist_ok=True)
    args.manifest.write_text(json.dumps(report,indent=2),encoding='utf-8',newline='\n')
    print(json.dumps({key:value for key,value in report.items() if key not in ('samples','rejected')},indent=2),flush=True)


if __name__=='__main__':main()
