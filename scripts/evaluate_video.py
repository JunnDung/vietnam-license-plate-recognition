"""Reproduce selected-target video measurements without changing weights or history."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from recognition import PlateEngine
from temporal import StreamConsensus
from scripts.camera import crop_region


def measure(engine, clip, fps, roi):
    path = (ROOT/clip['local_file']).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Video file must be inside the project.')
    if not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        with urllib.request.urlopen(clip['url'],timeout=60) as response:
            raw = response.read(100*1024*1024+1)
        if len(raw)>100*1024*1024 or hashlib.sha256(raw).hexdigest()!=clip['sha256']:
            raise ValueError('Source video exceeds limit or checksum changed.')
        path.write_bytes(raw)
    with path.open('rb') as file:
        if hashlib.file_digest(file,'sha256').hexdigest()!=clip['sha256']:
            raise ValueError('Video checksum mismatch.')
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError('Cannot decode video.')
    source_fps = cap.get(cv2.CAP_PROP_FPS)
    duration = cap.get(cv2.CAP_PROP_FRAME_COUNT)/source_fps
    tracker = StreamConsensus();session = tracker.session('evaluation')
    rows, stable_events, times = [], {}, []
    index = 0; expected = set(clip['selected_expected_plates']); seen = set(); stable_seen = set()
    start = time.perf_counter()
    try:
        while index/fps < duration-.0001:
            moment = index/fps;cap.set(cv2.CAP_PROP_POS_MSEC,moment*1000)
            valid,frame = cap.read()
            if not valid: break
            frame = crop_region(frame,roi)
            height,width = frame.shape[:2];scale=min(1,1280/max(width,height))
            if scale<1: frame=cv2.resize(frame,(round(width*scale),round(height*scale)))
            # Match browser JPEG submission, rather than evaluating pristine codec frames.
            _,encoded=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,90]);frame=cv2.imdecode(encoded,cv2.IMREAD_COLOR)
            inference_start=time.perf_counter();items=engine.predict(frame,confidence=.35)
            times.append((time.perf_counter()-inference_start)*1000)
            tracker.update(session,items,moment,frame.shape[1],frame.shape[0])
            for item in items:
                item.pop('crop');seen.add(item['plate'])
                if item['temporal']['status']=='stable':
                    stable_seen.add(item['plate']);key=item['temporal']['track_id']+':'+item['plate']
                    if key not in stable_events: stable_events[key]={'plate':item['plate'],'first':moment,'last':moment,'frames':0}
                    stable_events[key]['last']=moment;stable_events[key]['frames']+=1
            rows.append({'seconds':moment,'detections':items});index+=1
    finally: cap.release()
    return {'condition':clip['condition'],'roi_percent':roi,'duration_seconds':duration,'source_fps':source_fps,
            'sampled_frames':len(rows),'processing_seconds':round(time.perf_counter()-start,3),
            'pipeline_mean_ms':round(float(np.mean(times)),2),'pipeline_p95_ms':round(float(np.percentile(times,95)),2),
            'selected_targets':sorted(expected),'targets_read_in_any_frame':sorted(expected&seen),
            'targets_read_stably':sorted(expected&stable_seen),'missed_stable_targets':sorted(expected-stable_seen),
            'stable_events':list(stable_events.values()),'unverified_stable_plates':sorted(stable_seen-expected),'frames':rows}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,default=ROOT/'reports/video_ground_truth.json')
    parser.add_argument('--output',type=Path,default=ROOT/'reports/real_video.json');parser.add_argument('--device',default='auto')
    args=parser.parse_args();manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
    engine=PlateEngine(device=args.device);engine.predict(np.full((480,640,3),127,dtype=np.uint8))
    result={'date':'2026-10-06','weights_sha256':engine.detector_weights_sha256,'device':engine.device,
            'manifest_sha256':hashlib.sha256(args.manifest.read_bytes()).hexdigest(),'limitations':manifest['annotation'], 'clips':[]}
    for clip in manifest['clips']:
        for roi in ([None,clip['roi_percent']] if clip['roi_percent'] else [None]):
            measurement=measure(engine,clip,manifest['sampling_fps'],roi);measurement['file']=clip['file'];result['clips'].append(measurement)
            print(json.dumps({key:value for key,value in measurement.items() if key not in ('frames','stable_events')},ensure_ascii=False),flush=True)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')


if __name__ == '__main__':
    main()
