"""Freeze VNLP fine-tuning groups without reusing the published benchmark."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.prepare_ocr_benchmark import ARCHIVE_SHA256, SOURCE, parse_name, deduplicate

SEED='vnlp-finetune-20261102'


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def build_groups(rows):
    parents=list(range(len(rows)))
    def find(index):
        while parents[index]!=index:
            parents[index]=parents[parents[index]]
            index=parents[index]
        return index
    owners={}
    for index,row in enumerate(rows):
        keys=[('plate',row['plate']),('pixels',row['source_pixel_sha256']),('pixels',row['pixel_sha256'])]
        for key in keys:
            if key in owners:parents[find(index)]=find(owners[key])
            else:owners[key]=index
    groups=defaultdict(list)
    for index,row in enumerate(rows):groups[find(index)].append(row)
    return sorted([sorted(group,key=lambda row:row['member']) for group in groups.values()],
                  key=lambda group:group[0]['member'])


def assign_splits(rows,reserved_plates,reserved_sources,seed):
    result=[]
    for group in build_groups(rows):
        identity=digest('\0'.join(sorted({row['plate'] for row in group})))
        bucket=int(digest(seed+':'+identity)[:8],16)%10
        split='train' if bucket<8 else 'val' if bucket==8 else 'test'
        if any(row['plate'] in reserved_plates or row['source_pixel_sha256'] in reserved_sources
               or row['pixel_sha256'] in reserved_sources for row in group):split='excluded'
        result.extend(dict(row,group=identity,split=split) for row in group)
    return sorted(result,key=lambda row:row['member'])


def pixel_hash(image):
    return hashlib.sha256(str(image.size).encode()+image.tobytes()).hexdigest()


def write_csvs(samples,folder):
    for split in ('train','val'):
        with (folder/(split+'.csv')).open('w',encoding='utf-8',newline='') as file:
            writer=csv.writer(file);writer.writerow(['image_path','plate_text','plate_region'])
            writer.writerows((Path(row['image']).relative_to('data/ocr_training').as_posix(),row['plate'],'Vietnam')
                             for row in samples if row['split']==split)


def main():
    from PIL import Image
    parser=argparse.ArgumentParser()
    parser.add_argument('--archive',type=Path,default=ROOT/'data/raw/VNLP_detection.zip')
    parser.add_argument('--manifest',type=Path,default=ROOT/'reports/ocr_finetune_manifest.json')
    args=parser.parse_args()
    if args.manifest.exists():parser.error('Frozen manifest exists; preserve previous evidence.')
    with args.archive.open('rb') as file:
        if hashlib.file_digest(file,'sha256').hexdigest()!=ARCHIVE_SHA256:raise ValueError('Archive checksum mismatch')
    old=json.loads((ROOT/'reports/ocr_benchmark_manifest.json').read_text(encoding='utf-8'))
    legacy=json.loads((ROOT/'reports/ocr_ground_truth.json').read_text(encoding='utf-8'))
    reserved={row['plate'] for row in old['samples']}|{row['expected'] for row in legacy['samples']}
    reserved_pixels={row[key] for row in old['samples'] for key in ('source_pixel_sha256','pixel_sha256')}
    for row in legacy['samples']:
        with Image.open(ROOT/'data/plates'/row['image']) as image:
            image=image.convert('RGB')
            reserved_pixels.update((pixel_hash(image),pixel_hash(image.crop(row['bbox']))))
    folder=ROOT/'data/ocr_training';(folder/'crops').mkdir(parents=True,exist_ok=True)
    (folder/'sources').mkdir(exist_ok=True)
    rows,rejected=[],[]
    with zipfile.ZipFile(args.archive) as archive:
        names=sorted(n for n in archive.namelist() if n.lower().endswith('.jpg'))
        for index,name in enumerate(names):
            try:
                row=parse_name(name)
                with Image.open(io.BytesIO(archive.read(name))) as image:
                    image=image.convert('RGB');x0,y0,x1,y1=row['bbox']
                    if x1>image.width or y1>image.height:raise ValueError('Box exceeds source bounds')
                    crop=image.crop(row['bbox'])
                    if min(crop.size)<8:raise ValueError('Crop smaller than 8 pixels')
                    row.update(pixel_sha256=pixel_hash(crop),source_pixel_sha256=pixel_hash(image),size=list(crop.size))
                rows.append(row)
            except (ValueError,OSError,KeyError) as error:rejected.append({'member':name,'reason':str(error)})
            if (index+1)%5000==0:print(f'Audited {index+1}/{len(names)} sources',flush=True)
        unique,audit=deduplicate(rows)
        assigned=assign_splits(unique,reserved,reserved_pixels,SEED)
        selected=[r for r in assigned if r['split']=='train']
        evaluation=defaultdict(list)
        for row in assigned:
            if row['split'] in ('val','test'):evaluation[row['plate']].append(row)
        selected.extend(min(group,key=lambda row:digest(SEED+':'+row['member'])) for group in evaluation.values())
        selected.sort(key=lambda row:(row['split'],row['member']))
        counts=Counter(row['split'] for row in selected)
        if any(counts[split]<100 for split in ('train','val','test')):raise ValueError('Insufficient independent groups')
        print('Frozen selection before inference:',dict(counts),flush=True)
        for index,row in enumerate(selected):
            identity=digest(row['member'])[:24]
            row['image']=f'data/ocr_training/crops/{identity}.png'
            raw=archive.read(row['member'])
            with Image.open(io.BytesIO(raw)) as image:image.convert('RGB').crop(row['bbox']).save(ROOT/row['image'])
            row['image_sha256']=hashlib.sha256((ROOT/row['image']).read_bytes()).hexdigest()
            row['source_sha256']=hashlib.sha256(raw).hexdigest()
            if row['split']!='train':
                row['source_image']=f'data/ocr_training/sources/{identity}.jpg'
                (ROOT/row['source_image']).write_bytes(raw)
            if (index+1)%5000==0:print(f'Prepared {index+1}/{len(selected)} crops',flush=True)
    write_csvs(selected,folder)
    for key in ('plate','group','source_pixel_sha256','pixel_sha256'):
        ownership={}
        for row in selected:
            if key in row and row[key] in ownership:assert ownership[row[key]]==row['split']
            ownership[row[key]]=row['split']
    report={'source':SOURCE,'archive_sha256':ARCHIVE_SHA256,'seed':SEED,
        'protocol':'Connected components of plate IDs and exact full-source/crop pixels; component hash modulo10:0-7 train,8 validation,9 final test. All training captures, one deterministic capture per evaluation plate. No inference-based exclusions.',
        'reserved_plates':sorted(reserved),'reserved_source_and_crop_pixels':len(reserved_pixels),
        'published_manifest_sha256':hashlib.sha256((ROOT/'reports/ocr_benchmark_manifest.json').read_bytes()).hexdigest(),
        'source_images':len(names),'audit':audit,'rejected':rejected,
        'excluded_reserved_rows':sum(r['split']=='excluded' for r in assigned),
        'counts':{s:{'images':counts[s],'plates':len({r['plate'] for r in selected if r['split']==s}),
                     'two_lines':sum(r['square'] for r in selected if r['split']==s)} for s in ('train','val','test')},
        'limitations':'Filename labels not independently human audited. Upstream OCR pretraining overlap unknown. No capture/session metadata; split is by plate and exact pixels, not proof of camera-independent generalization. Dataset redistribution license unconfirmed; images remain local.',
        'csv_columns':['image_path','plate_text','plate_region'],
        'csv_sha256':{s:hashlib.sha256((folder/(s+'.csv')).read_bytes()).hexdigest() for s in ('train','val')},
        'samples':selected}
    args.manifest.parent.mkdir(parents=True,exist_ok=True)
    args.manifest.write_text(json.dumps(report,indent=2),encoding='utf-8',newline='\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('samples','reserved_plates','rejected')},indent=2),flush=True)
    print('Manifest SHA256',hashlib.sha256(args.manifest.read_bytes()).hexdigest(),flush=True)


if __name__=='__main__':main()
