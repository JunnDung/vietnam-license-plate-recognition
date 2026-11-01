"""YOLO detector + pretrained plate OCR. No fabricated text or registry lookup."""
import io
import hashlib
import math
import os
import re
import threading
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 16_000_000


def decode_image(raw):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('Ảnh phải có dung lượng từ 1 byte đến 10 MB.')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('JPEG', 'PNG', 'WEBP'):
                raise ValueError('Chỉ hỗ trợ JPG, PNG và WebP.')
            if image.width * image.height > MAX_PIXELS or min(image.size) < 32:
                raise ValueError('Ảnh phải có cạnh ít nhất 32 px và tối đa 16 triệu pixel.')
            rgb = np.asarray(ImageOps.exif_transpose(image).convert('RGB'))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError('Không đọc được ảnh. Hãy kiểm tra định dạng và nội dung file.') from error
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def normalize_plate(text):
    return re.sub(r'[^A-Z0-9]', '', text.upper())


def is_vietnamese_plate(text):
    # Common civilian formats only; confidence is not proof that a plate is registered.
    return bool(re.fullmatch(r'\d{2}(?:[A-Z]{1,2}|[A-Z]\d)\d{4,5}', text))


def format_plate(text):
    if not is_vietnamese_plate(text):
        return text
    match = re.fullmatch(r'(\d{2}(?:[A-Z]{1,2}|[A-Z]\d))(\d{4,5})', text)
    prefix, digits = match.groups()
    return prefix + '-' + (digits[:3] + '.' + digits[3:] if len(digits) == 5 else digits)


def jpeg_bytes(image):
    success, data = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not success:
        raise ValueError('Không mã hóa được ảnh.')
    return data.tobytes()


def crop_quality(crop, min_detail=25., min_brightness=40.):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    resized = cv2.resize(gray, (160, max(16, min(160, round(gray.shape[0]*160/gray.shape[1])))))
    detail = float(cv2.Laplacian(resized, cv2.CV_64F).var())
    # ponytail: texture is a blur proxy, not calibrated readability; tune thresholds on the gate camera.
    issues = []
    if brightness < min_brightness: issues.append('low_light')
    if detail < min_detail: issues.append('low_detail')
    if crop.shape[0] < 24 or crop.shape[1] < 48: issues.append('small_plate')
    return {'brightness': round(brightness, 1), 'detail_score': round(detail, 1), 'issues': issues}


def flatten_two_lines(crop):
    height, width = crop.shape[:2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    # ponytail: horizontal projection handles near-upright plates; add trained keypoints for severe tilt.
    left, right = max(1, int(width * .12)), max(2, int(width * .88))
    start, end = int(height * .35), int(height * .65)
    split = start + int(np.argmin(binary[start:end, left:right].mean(axis=1)))
    top, bottom = crop[:split], crop[split:]
    target = max(top.shape[0], bottom.shape[0])
    pieces = [cv2.resize(piece, (round(piece.shape[1] * target / piece.shape[0]), target))
              for piece in (top, bottom)]
    gap = np.full((target, max(2, target // 8), 3), 220, dtype=np.uint8)
    return np.concatenate((pieces[0], gap, pieces[1]), axis=1)


def rectify_plate(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    quad = cv2.approxPolyDP(contour, .03 * cv2.arcLength(contour, True), True)
    # shortcut: only bright, visible four-corner borders; retain original crops for other plates.
    if len(quad) != 4 or not cv2.isContourConvex(quad) or cv2.contourArea(quad) < .4 * gray.size:
        return None
    points = quad.reshape(4, 2).astype(np.float32)
    sums, differences = points.sum(axis=1), np.diff(points, axis=1).ravel()
    points = points[[sums.argmin(), differences.argmin(), sums.argmax(), differences.argmax()]]
    if len(np.unique(points, axis=0)) != 4:
        return None
    top_left, top_right, bottom_right, bottom_left = points
    if max(abs(top_right[1]-top_left[1]), abs(bottom_right[1]-bottom_left[1]),
           abs(top_left[0]-bottom_left[0]), abs(top_right[0]-bottom_right[0])) <= 1:
        return None
    width = round(max(np.linalg.norm(top_right-top_left), np.linalg.norm(bottom_right-bottom_left)))
    height = round(max(np.linalg.norm(bottom_left-top_left), np.linalg.norm(bottom_right-top_right)))
    if min(width, height) < 8:
        return None
    target = np.array([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]], np.float32)
    return cv2.warpPerspective(crop, cv2.getPerspectiveTransform(points, target), (width, height))


class PlateEngine:
    def __init__(self, detector=None, ocr=None, device='cpu'):
        from ultralytics import YOLO
        from fast_plate_ocr import LicensePlateRecognizer
        import onnxruntime as ort
        import torch

        torch.set_num_threads(2)
        self.detector_weights_sha256 = hashlib.sha256((ROOT/'models/plate_detector.pt').read_bytes()).hexdigest() if detector is None else None
        self.detector = detector if detector is not None else YOLO(str(ROOT / 'models/plate_detector.pt'))
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.ocr = ocr if ocr is not None else LicensePlateRecognizer(
            onnx_model_path=ROOT / 'models/plate_ocr.onnx',
            plate_config_path=ROOT / 'models/plate_ocr_config.yaml',
            providers=['CPUExecutionProvider'], sess_options=options)
        self.device = ('0' if torch.cuda.is_available() else 'cpu') if device == 'auto' else device
        self.min_detail = float(os.getenv('PLATE_MIN_DETAIL', '25'))
        self.min_brightness = float(os.getenv('PLATE_MIN_BRIGHTNESS', '40'))
        if not math.isfinite(self.min_detail) or self.min_detail < 0 or not 0 <= self.min_brightness <= 255:
            raise ValueError('Invalid image quality thresholds.')
        # ponytail: one inference at a time on a 6 GB workstation; use worker queues if throughput requires it.
        self.lock = threading.Lock()

    def read_crop(self, crop, square=False):
        if min(crop.shape[:2]) < 8:
            return {'plate': '', 'raw_text': '', 'ocr_confidence': 0., 'valid_format': False}
        variants = [crop]
        if square or crop.shape[1] / crop.shape[0] < 2.2:
            variants.append(flatten_two_lines(crop))
        lab = cv2.cvtColor(variants[-1], cv2.COLOR_BGR2LAB)
        lab[:, :, 0] = cv2.createCLAHE(clipLimit=2., tileGridSize=(4, 4)).apply(lab[:, :, 0])
        variants.append(cv2.cvtColor(lab, cv2.COLOR_LAB2BGR))
        if square or crop.shape[1] / crop.shape[0] < 2.2:
            rectified = rectify_plate(crop)
            if rectified is not None:
                variants.append(flatten_two_lines(rectified))
        # FastPlateOCR's RGB model assumes in-memory arrays already use RGB.
        predictions = self.ocr.run([cv2.cvtColor(image, cv2.COLOR_BGR2RGB) for image in variants], return_confidence=True)
        candidates = []
        for prediction in predictions:
            text = normalize_plate(prediction.plate)
            slots = [match.start() for match in re.finditer(r'[A-Z0-9]', prediction.plate.upper())]
            probabilities = np.asarray(prediction.char_probs, dtype=float)[slots]
            confidence = float(probabilities.mean()) if len(probabilities) else 0.
            candidates.append({'plate': text, 'raw_text': prediction.plate,
                               'ocr_confidence': round(confidence, 4), 'valid_format': is_vietnamese_plate(text)})
        best = max(candidates, key=lambda item: (item['valid_format'], item['ocr_confidence']))
        best['ocr_disagreement'] = len({item['plate'] for item in candidates if item['valid_format']}) > 1
        return best

    def predict(self, image, confidence=.35):
        height, width = image.shape[:2]
        with self.lock:
            result = self.detector.predict(image, imgsz=640, conf=confidence, device=self.device,
                                           max_det=20, verbose=False)[0]
            detections = []
            for box in result.boxes:
                x0, y0, x1, y1 = box.xyxy[0].cpu().numpy().tolist()
                pad_x, pad_y = (x1-x0) * .035, (y1-y0) * .035
                x0, y0 = max(0, int(x0-pad_x)), max(0, int(y0-pad_y))
                x1, y1 = min(width, int(x1+pad_x)), min(height, int(y1+pad_y))
                if x1 <= x0 or y1 <= y0:
                    continue
                crop = image[y0:y1, x0:x1]
                square = int(box.cls.item()) == 1
                reading = self.read_crop(crop, square=square)
                quality = crop_quality(crop, self.min_detail, self.min_brightness)
                reading.update({'bbox': [x0, y0, x1, y1], 'display_plate': format_plate(reading['plate']),
                                'detector_confidence': round(float(box.conf.item()), 4),
                                'layout': 'two_lines' if square else 'one_line',
                                'needs_review': not reading['valid_format'] or reading['ocr_confidence'] < .8 or bool(quality['issues']) or reading.get('ocr_disagreement', False),
                                'quality': quality,
                                'crop': crop})
                detections.append(reading)
            return detections
