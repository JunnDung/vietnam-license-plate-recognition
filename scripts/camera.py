"""Read webcam, video or RTSP locally and submit bounded frames to the API."""
import argparse
import json
import math
import os
import time
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


def best_frame(capture, first, count):
    best, score, sampled = first, sharpness(first), 1
    best_time = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000
    for _ in range(count - 1):
        valid, candidate = capture.read()
        if not valid:
            break
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
    parser.add_argument('--interval', type=float, default=3)
    parser.add_argument('--burst', type=int, default=3, help='Pick the sharpest of 1–15 consecutive frames')
    parser.add_argument('--save', action='store_true', help='Store frames with detections in history')
    args = parser.parse_args()
    if not math.isfinite(args.interval) or args.interval <= 0:
        parser.error('--interval must be positive')
    if not 1 <= args.burst <= 15:
        parser.error('--burst must be between 1 and 15')
    source = int(args.source) if args.source.isdecimal() else args.source
    is_video = isinstance(source, str) and Path(source).is_file()
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise SystemExit('Cannot open the camera/video source.')
    next_frame = 0
    try:
        with httpx.Client(timeout=120, headers={'X-API-Key': os.getenv('PLATE_API_KEY', '')}) as client:
            while True:
                valid, frame = capture.read()
                if not valid:
                    break
                frame_time = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000 if is_video else time.monotonic()
                if frame_time < next_frame:
                    continue
                frame, score, sampled, selected_time = best_frame(capture, frame, args.burst)
                if frame.shape[1] > 1280:
                    frame = cv2.resize(frame, (1280, round(frame.shape[0] * 1280 / frame.shape[1])))
                success, data = cv2.imencode('.jpg', frame)
                if not success:
                    continue
                response = client.post(args.api.rstrip('/') + '/api/recognize',
                                       files={'file': ('frame.jpg', data.tobytes(), 'image/jpeg')},
                                       data={'source': 'camera-cli', 'save': str(args.save).lower()})
                response.raise_for_status()
                result = response.json()
                print(json.dumps({'latency_ms': result['latency_ms'], 'detections': result['detections'],
                                  'frames_compared': sampled, 'sharpness': round(score, 2),
                                  'video_time': selected_time if is_video else None}, ensure_ascii=False))
                next_frame = frame_time + args.interval if is_video else time.monotonic() + args.interval
    except KeyboardInterrupt:
        pass
    finally:
        capture.release()


if __name__ == '__main__':
    main()
