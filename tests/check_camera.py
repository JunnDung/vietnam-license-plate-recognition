"""Live API: legacy 0/3/6 sampling and default 5 FPS must preserve video timestamps."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory() as folder:
        video = Path(folder) / 'camera.avi'
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'), 5, (320, 240))
        assert writer.isOpened()
        for _ in range(35):
            writer.write(np.full((240, 320, 3), 127, dtype=np.uint8))
        writer.release()
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/camera.py'), '--source', str(video), '--interval', '3'],
                                cwd=ROOT, capture_output=True, text=True, check=True)
        frames = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        assert len(frames) == 3, f'Expected 3 sampled frames, got {len(frames)}'
        assert all(item['detections'] == [] for item in frames), 'Blank video should not fabricate plates'
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/camera.py'), '--source', str(video)],
                                cwd=ROOT, capture_output=True, text=True, check=True)
        faster = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        assert len(faster) == 35, f'Expected all 35 frames at 5 source FPS, got {len(faster)}'
        assert all(abs(item['video_time']-index/5)<.001 for index,item in enumerate(faster))
        assert all(item['detections']==[] for item in faster)
        print('PASS: legacy 0/3/6 seconds and default 5 FPS process correct timestamps; blank video has no plates.')


if __name__ == '__main__':
    main()
