"""Read webcam, video or RTSP locally and submit bounded frames to the API."""
import argparse
import json
import math
import os
import time
import uuid
from pathlib import Path

import cv2
import httpx


def sharpness(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if gray.shape[1] > 320:
        gray = cv2.resize(gray, (320, max(1, round(gray.shape[0] * 320 / gray.shape[1]))))
    # ponytail: whole-frame sharpness can favor background edges; use a gate ROI after camera calibration.
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def crop_region(frame, roi):
    if roi is None:
        return frame
    height, width = frame.shape[:2]
    x,y,w,h = roi
    result = frame[round(y*height/100):round((y+h)*height/100), round(x*width/100):round((x+w)*width/100)]
    if min(result.shape[:2]) < 32:
        raise ValueError('ROI is smaller than 32 pixels; choose a larger region.')
    return result


def best_frame(capture, first, count, roi=None):
    best, score, sampled = first, sharpness(first), 1
    best_time = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000
    for _ in range(count - 1):
        valid, candidate = capture.read()
        if not valid:
            break
        candidate = crop_region(candidate, roi)
        sampled += 1
        candidate_score = sharpness(candidate)
        if candidate_score > score:
            best, score = candidate, candidate_score
            best_time = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000
    return best, score, sampled, best_time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default='0', help='Webcam number, local video path or RTSP URL')
    parser.add_argument('--api', default='http://127.0.0.1:8000')
    parser.add_argument('--fps', type=float, default=5, help='Target recognition rate (1–10 frames/second); actual rate depends on API')
    parser.add_argument('--interval', type=float, help='Legacy sampling interval in seconds; overrides --fps')
    parser.add_argument('--burst', type=int, default=3, help='Pick the sharpest of 1–15 consecutive frames')
    parser.add_argument('--save', action='store_true', help='Store frames with detections in history')
    parser.add_argument('--roi', help='Camera/video region in percent: x,y,width,height; saves the cropped region')
    args = parser.parse_args()
    if not math.isfinite(args.fps) or not 1 <= args.fps <= 10:
        parser.error('--fps must be between 1 and 10')
    args.interval = args.interval if args.interval is not None else 1 / args.fps
    if not math.isfinite(args.interval) or args.interval <= 0:
        parser.error('--interval must be positive')
    if not 1 <= args.burst <= 15:
        parser.error('--burst must be between 1 and 15')
    roi = None
    if args.roi:
        try:
            roi = [float(value) for value in args.roi.split(',')]
            x,y,w,h = roi
            if not all(math.isfinite(value) for value in roi) or min(x,y)<0 or min(w,h)<=0 or x+w>100 or y+h>100:
                raise ValueError()
        except ValueError:
            parser.error('--roi must be x,y,width,height inside 0–100 percent')
    source = int(args.source) if args.source.isdecimal() else args.source
    is_video = isinstance(source, str) and Path(source).is_file()
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise SystemExit('Cannot open the camera/video source.')
    source_fps = capture.get(cv2.CAP_PROP_FPS)
    burst = min(args.burst, max(1, int(source_fps * args.interval))) if is_video and math.isfinite(source_fps) and source_fps > 0 else args.burst
    if not is_video:
        capture.set(cv2.CAP_PROP_FPS, 30)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    next_frame = 0
    stream_id, stream_started = str(uuid.uuid4()), time.monotonic()
    try:
        with httpx.Client(timeout=30, headers={'X-API-Key': os.getenv('PLATE_API_KEY', '')}) as client:
            while True:
                valid, frame = capture.read()
                if not valid:
                    break
                frame_time = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000 if is_video else time.monotonic()
                if frame_time + 1e-6 < next_frame:
                    continue
                started = time.monotonic()
                frame, score, sampled, selected_time = best_frame(capture, crop_region(frame,roi), burst, roi)
                scale = min(1,1280/max(frame.shape[:2]))
                if scale < 1:
                    frame = cv2.resize(frame, (round(frame.shape[1]*scale), round(frame.shape[0]*scale)))
                success, data = cv2.imencode('.jpg', frame)
                if not success:
                    continue
                response = client.post(args.api.rstrip('/') + '/api/recognize',
                                       files={'file': ('frame.jpg', data.tobytes(), 'image/jpeg')},
                                       data={'source': 'video-cli' if is_video else 'camera-cli', 'save': str(args.save).lower(),
                                             'stream_id':stream_id, 'sample_time':selected_time if is_video else started-stream_started})
                response.raise_for_status()
                result = response.json()
                print(json.dumps({'latency_ms': result['latency_ms'], 'detections': result['detections'],
                                  'frames_compared': sampled, 'sharpness': round(score, 2),
                                  'processing_ms': round((time.monotonic()-started)*1000, 1),
                                  'video_time': selected_time if is_video else None}, ensure_ascii=False), flush=True)
                next_frame = frame_time + args.interval if is_video else started + args.interval
    except KeyboardInterrupt:
        pass
    finally:
        capture.release()


if __name__ == '__main__':
    main()
