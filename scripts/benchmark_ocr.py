"""Paired OCR accuracy with denominators, uncertainty and warm wall-clock latency."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def edit_distance(a,b):
    previous=list(range(len(b)+1))
    for i,char in enumerate(a,1):
        current=[i]
        for j,other in enumerate(b,1):current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(char!=other)))
        previous=current
    return previous[-1]


def percentile(values,fraction):
    ordered=sorted(values);index=(len(ordered)-1)*fraction
    lower=math.floor(index);upper=math.ceil(index)
    return ordered[lower]+(ordered[upper]-ordered[lower])*(index-lower)


def summarize(rows):
    if not rows:raise ValueError('Evaluation cannot be empty')
    count=len(rows);correct=sum(row['expected']==row['predicted'] for row in rows)
    characters=sum(len(row['expected']) for row in rows)
    if not characters:raise ValueError('Empty reference labels')
    errors=sum(edit_distance(row['expected'],row['predicted']) for row in rows)
    probability=correct/count;z=1.959963984540054
    center=(probability+z*z/(2*count))/(1+z*z/count)
    margin=z*math.sqrt(probability*(1-probability)/count+z*z/(4*count*count))/(1+z*z/count)
    times=[row['latency_ms'] for row in rows]
    return {'samples':count,'correct':correct,'exact_match':probability,'character_errors':errors,'characters':characters,
            'cer':errors/characters,'wilson95':[max(0,center-margin),min(1,center+margin)],
            'latency_mean_ms':statistics.mean(times),'latency_p50_ms':statistics.median(times),
            'latency_p95_ms':percentile(times,.95),'serial_crops_per_second':1000/statistics.mean(times)}


def main():
    import cv2
    import numpy as np
    import onnxruntime
    from recognition import PlateEngine
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',type=Path,default=ROOT/'reports/ocr_benchmark_manifest.json')
    parser.add_argument('--split',choices=['dev','test'],default='dev')
    parser.add_argument('--baseline-module',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Output exists; preserve previous measurements.')
    manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
    identities=[row['plate'] for row in manifest['samples']]
    if len(set(identities)) != len(identities):raise ValueError('Repeated plate identity in manifest')
    samples=[row for row in manifest['samples'] if row['split']==args.split]
    if not samples:parser.error('No selected samples')
    # Guard the exact manifest and pixels. Never silently drop failed images.
    for row in samples:
        path=(ROOT/row['image']).resolve()
        if not path.is_relative_to(ROOT/'data'):raise ValueError('Sample outside data directory')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['image_sha256']:raise ValueError('Image checksum mismatch')
    spec=importlib.util.spec_from_file_location('shipped_baseline',args.baseline_module)
    baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
    baseline.ROOT=ROOT
    candidate=PlateEngine(device='cpu')
    old=baseline.PlateEngine(detector=candidate.detector,ocr=candidate.ocr,device='cpu')
    # Crop OCR uses the same ONNX CPU session, detector is not invoked/timed.
    engines={'baseline':old,'candidate':candidate};predictions={name:[] for name in engines}
    for square in (False,True):
        layout_samples=[row for row in samples if row['square']==square]
        if not layout_samples:continue
        probe=cv2.imread(str(ROOT/layout_samples[0]['image']))
        for engine in engines.values():
            for _ in range(5):engine.read_crop(probe,square=square)
    for index,row in enumerate(samples):
        image=cv2.imread(str(ROOT/row['image']))
        if image is None:raise ValueError('Image decode failed')
        # Alternate order to reduce systematic timing order bias.
        for name in (list(engines) if index%2==0 else list(reversed(engines))):
            start=time.perf_counter();reading=engines[name].read_crop(image,square=row['square'])
            elapsed=(time.perf_counter()-start)*1000
            predictions[name].append({'member':row['member'],'expected':row['plate'],'predicted':reading['plate'],
                'square':row['square'],'latency_ms':elapsed,'ocr_confidence':reading['ocr_confidence'],
                'ocr_disagreement':reading.get('ocr_disagreement',False)})
        if (index+1)%100==0:print(f'Scored {index+1}/{len(samples)} paired crops',flush=True)
    report={'split':args.split,'created_at':datetime.now(timezone.utc).isoformat(),
            'manifest_sha256':hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
            'baseline_code_sha256':hashlib.sha256(args.baseline_module.read_bytes()).hexdigest(),
            'candidate_code_sha256':hashlib.sha256((ROOT/'recognition.py').read_bytes()).hexdigest(),
            'ocr_sha256':hashlib.sha256((ROOT/'models/plate_ocr.onnx').read_bytes()).hexdigest(),
            'ocr_config_sha256':hashlib.sha256((ROOT/'models/plate_ocr_config.yaml').read_bytes()).hexdigest(),
            'protocol':'Crop-only exact match and CER; all manifest-selected samples, batch variants per crop, CPU ONNX Runtime 2 threads, 5 warmups per layout per implementation, alternating order. Timing includes crop transforms/OCR/decoding, excludes file IO and detector/API.',
            'runtime':{'onnxruntime':onnxruntime.__version__,'numpy':np.__version__,'opencv':cv2.__version__,
                       'python':platform.python_version(),'system':platform.platform(),'processor':platform.processor()},
            'limitations':manifest['limitations'],'results':{}}
    for name,rows in predictions.items():
        report['results'][name]={**summarize(rows),'one_line':summarize([r for r in rows if not r['square']]) if any(not r['square'] for r in rows) else None,
                                  'two_lines':summarize([r for r in rows if r['square']]) if any(r['square'] for r in rows) else None,'predictions':rows}
    paired=list(zip(predictions['baseline'],predictions['candidate']))
    report['paired']={'fixed':sum(a['predicted']!=a['expected'] and b['predicted']==b['expected'] for a,b in paired),
                      'regressed':sum(a['predicted']==a['expected'] and b['predicted']!=b['expected'] for a,b in paired)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8',newline='\n')
    print(json.dumps({name:summarize(rows) for name,rows in predictions.items()},indent=2),flush=True)


if __name__=='__main__':main()
