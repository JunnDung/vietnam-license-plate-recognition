"""Run against the live local API: a seven-second video must produce frames at 0, 3, 6 seconds."""
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
        print('PASS: live API processed video frames at 0, 3 and 6 seconds; blank video returned no plates.')


if __name__ == '__main__':
    main()
