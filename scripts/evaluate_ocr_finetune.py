"""Paired crop and annotated-target evaluation; never select using final test."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.benchmark_ocr import summarize, percentile
from scripts.train_ocr import sha


def adoption_checks(base,candidate,legacy_base,legacy_candidate):
    if base['samples']!=candidate['samples']:raise ValueError('Paired denominators differ')
    return {
        'exact_gain_at_least_half_percentage_point':candidate['correct']-base['correct']>=math.ceil(base['samples']*.005),
        'cer_no_regression':candidate['cer']<=base['cer'],
        'two_line_no_regression':candidate['two_lines']['correct']>=base['two_lines']['correct'],
        'p95_within_ten_percent':candidate['latency_p95_ms']<=base['latency_p95_ms']*1.1,
        'pipeline_no_regression':candidate['pipeline_exact_match']>=base['pipeline_exact_match'],
        'legacy_clean_no_regression':all(legacy_candidate[key]>=legacy_base[key] for key in ('crop','pipeline'))}


def match_target(detections,bbox):
    from scripts.evaluate_robustness import iou
    if not detections:return None
    best=max(detections,key=lambda row:iou(row['bbox'],bbox))
    overlap=iou(best['bbox'],bbox)
    return dict(best,matched_iou=overlap) if overlap>=.5 else None


def read_single(ocr,crop):
    import cv2
    from recognition import decode_predictions
    if min(crop.shape[:2])<8:
        return {'plate':'','raw_text':'','ocr_confidence':0.,'valid_format':False,'ocr_disagreement':False}
    return decode_predictions(ocr.run([cv2.cvtColor(crop,cv2.COLOR_BGR2RGB)],return_confidence=True))


def paired_counts(first,second):
    fixed=sum(a['predicted']!=a['expected'] and b['predicted']==b['expected'] for a,b in zip(first,second))
    regressed=sum(a['predicted']==a['expected'] and b['predicted']!=b['expected'] for a,b in zip(first,second))
    n=fixed+regressed
    p=min(1.,2*sum(math.comb(n,k) for k in range(min(fixed,regressed)+1))/2**n) if n else 1.
    return {'fixed':fixed,'regressed':regressed,'exact_mcnemar_two_sided_p':p}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--weights',type=Path,required=True)
    parser.add_argument('--split',choices=('val','test','regression'),default='val')
    parser.add_argument('--mode',choices=('both','single','variants'),default='both')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--device',default='auto')
    args=parser.parse_args()
    if args.output.exists():parser.error('Output exists; preserve measured evidence.')
    if args.split!='val' and args.mode=='both':parser.error('Select one mode before final/regression evaluation')
    import cv2
    import numpy as np
    import onnxruntime as ort
    import torch
    from fast_plate_ocr import LicensePlateRecognizer
    from scripts.evaluate_ocr import score
    from scripts.evaluate_robustness import corrupt
    manifest_path=ROOT/'reports'/('ocr_benchmark_manifest.json' if args.split=='regression' else 'ocr_finetune_manifest.json')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    samples=[r for r in manifest['samples'] if r['split']==('test' if args.split=='regression' else args.split)]
    if not samples or len({r['plate'] for r in samples})!=len(samples):raise ValueError('Evaluation requires unique nonempty plate IDs')
    for row in samples:
        for key,checksum in (('image','image_sha256'),('source_image','source_sha256')):
            path=(ROOT/row[key]).resolve()
            if not path.is_relative_to(ROOT/'data'):raise ValueError('Unsafe evaluation path')
            if sha(path)!=row[checksum]:raise ValueError('Evaluation image checksum mismatch')
    baseline_path=ROOT/'.local/ocr-finetune/baseline_recognition.py'
    if sha(baseline_path)!='0a455c02789b627be008cd3cffc3b570fc7218dab325ee4140f181f8ee74795b':
        raise ValueError('Expected frozen 1.4.0 baseline source')
    if sha(ROOT/'models/plate_ocr.onnx')!='384bbbd2cea3ef54761d3df70822ef3a349ee1a112aeafddbe0e3ba06bc6e47b':
        raise ValueError('Baseline OCR differs from published checkpoint')
    spec=importlib.util.spec_from_file_location('ocr_baseline_14',baseline_path)
    base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base);base.ROOT=ROOT
    old=base.PlateEngine(device=args.device)
    options=ort.SessionOptions();options.intra_op_num_threads=2
    trained=LicensePlateRecognizer(onnx_model_path=args.weights,
        plate_config_path=ROOT/'models/training/cct_s_v2_global_plate_config.yaml',
        providers=['CPUExecutionProvider'],sess_options=options)
    engines={'baseline':old}
    for mode in (('single','variants') if args.mode=='both' else (args.mode,)):
        engine=base.PlateEngine(detector=old.detector,ocr=trained,device=old.device)
        if mode=='single':engine.read_crop=lambda crop,square=False:read_single(trained,crop)
        engines[mode]=engine
    for square in (False,True):
        probe=next(row for row in samples if row['square']==square)
        crop=cv2.imread(str(ROOT/probe['image']))
        for engine in engines.values():
            for _ in range(5):engine.read_crop(crop,square=square)
    old.detector.predict(np.zeros((640,640,3),np.uint8),imgsz=640,conf=.35,device=old.device,max_det=20,verbose=False)
    predictions={name:[] for name in engines};names=list(engines)
    for index,row in enumerate(samples):
        crop=cv2.imread(str(ROOT/row['image']));image=cv2.imread(str(ROOT/row['source_image']))
        if crop is None or image is None:raise ValueError('Image decode failed')
        order=names[index%len(names):]+names[:index%len(names)]
        readings={}
        for name in order:
            start=time.perf_counter();reading=engines[name].read_crop(crop,square=row['square'])
            elapsed=(time.perf_counter()-start)*1000
            readings[name]={'member':row['member'],'expected':row['plate'],'predicted':reading['plate'],
                'square':row['square'],'group':row.get('group'), 'latency_ms':elapsed,
                'ocr_confidence':reading['ocr_confidence'],'ocr_disagreement':reading.get('ocr_disagreement',False)}
        for name in order:
            start=time.perf_counter();detections=engines[name].predict(image)
            elapsed=(time.perf_counter()-start)*1000;matched=match_target(detections,row['bbox'])
            readings[name].update(pipeline_ms=elapsed,target_detected=matched is not None,
                pipeline_predicted=matched['plate'] if matched else '',matched_iou=matched['matched_iou'] if matched else 0.,
                pipeline_correct=bool(matched and matched['plate']==row['plate']),detections_in_frame=len(detections))
            predictions[name].append(readings[name])
        if (index+1)%100==0:print(f'Scored {index+1}/{len(samples)} crops and full-image targets',flush=True)
    report={'split':args.split,'created_at':datetime.now(timezone.utc).isoformat(),'mode':args.mode,
        'manifest_sha256':sha(manifest_path),'baseline_source_sha256':sha(baseline_path),
        'candidate_weights_sha256':sha(args.weights),'candidate_path':str(args.weights.resolve().relative_to(ROOT)),
        'inference_source_sha256':sha(ROOT/'recognition.py'),'evaluation_source_sha256':sha(Path(__file__)),
        'detector_weights_sha256':sha(ROOT/'models/plate_detector.pt'),
        'baseline_ocr_sha256':sha(ROOT/'models/plate_ocr.onnx'),'ocr_config_sha256':sha(ROOT/'models/training/cct_s_v2_global_plate_config.yaml'),
        'protocol':'All selected unique plate targets. Crop exact/CER includes empty predictions. Full-image target match selects highest IoU>=0.5 without using text. No full-scene precision claim. 5 crop warmups per layout/engine and 1 detector warmup; rotating engine order. CPU ONNX2 threads, detector640/conf0.35/max20; timing excludes file IO/HTTP/storage, pipeline timing includes detector/OCR/quality.',
        'runtime':{'onnxruntime':ort.__version__,'opencv':cv2.__version__,'numpy':np.__version__,
            'torch':torch.__version__,'python':platform.python_version(),'processor':platform.processor(),
            'system':platform.platform(),'detector_device':old.device,'gpu':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None},
        'limitations':manifest['limitations']+' Partially annotated scenes; extra detections are not scored as false positives. Wilson/McNemar assume independent target outcomes; capture dependencies are not fully modeled.',
        'results':{},'paired':{}}
    for name,rows in predictions.items():
        times=[r['pipeline_ms'] for r in rows]
        report['results'][name]={**summarize(rows),
            'one_line':summarize([r for r in rows if not r['square']]),
            'two_lines':summarize([r for r in rows if r['square']]),
            'target_detection_recall_iou50':sum(r['target_detected'] for r in rows)/len(rows),
            'pipeline_correct':sum(r['pipeline_correct'] for r in rows),
            'pipeline_exact_match':sum(r['pipeline_correct'] for r in rows)/len(rows),
            'pipeline_p50_ms':float(np.median(times)),'pipeline_p95_ms':percentile(times,.95),'predictions':rows}
        if name!='baseline':report['paired'][name]=paired_counts(predictions['baseline'],rows)
    if args.split=='val':
        labels=json.loads((ROOT/'reports/ocr_ground_truth.json').read_text(encoding='utf-8'))
        legacy={name:score(engine,labels,'original') for name,engine in engines.items()}
        report['legacy_clean']=legacy;report['adoption_checks']={}
        for name in names[1:]:
            before=legacy['baseline'];after=legacy[name]
            report['adoption_checks'][name]=adoption_checks(report['results']['baseline'],report['results'][name],
                {'crop':round(before['exact_match']*before['samples']),'pipeline':round(before['pipeline_exact_match']*before['samples'])},
                {'crop':round(after['exact_match']*after['samples']),'pipeline':round(after['pipeline_exact_match']*after['samples'])})
        report['synthetic_stress']={}
        stress=sorted(samples,key=lambda r:hashlib.sha256(('stress-20261102:'+r['member']).encode()).hexdigest())[:200]
        for condition in ('synthetic_dark','synthetic_rain_fog','synthetic_motion_blur'):
            result={name:[] for name in engines}
            for index,row in enumerate(stress):
                image=corrupt(cv2.imread(str(ROOT/row['image'])),condition,index)
                for name,engine in engines.items():
                    start=time.perf_counter();reading=engine.read_crop(image,square=row['square'])
                    result[name].append({'expected':row['plate'],'predicted':reading['plate'],'latency_ms':(time.perf_counter()-start)*1000})
            report['synthetic_stress'][condition]={name:summarize(rows) for name,rows in result.items()}
        report['synthetic_stress_selection']='First200 validation targets by SHA256(stress-20261102:member); synthetic only, all included after corruption.'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8',newline='\n')
    print(json.dumps({name:{k:v for k,v in result.items() if k not in ('predictions','one_line','two_lines')} for name,result in report['results'].items()},indent=2),flush=True)
    if 'adoption_checks' in report:print(json.dumps(report['adoption_checks'],indent=2),flush=True)


if __name__=='__main__':main()
