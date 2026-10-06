`plate_detector.pt` is the YOLO11n checkpoint fine-tuned locally by `scripts/train.py`.
Its hash and held-out test metrics are in `reports/training.json`.

OCR is pretrained CCT S v2 from [fast-plate-ocr](https://github.com/ankandrew/fast-plate-ocr).
Run `python scripts/download_ocr.py` to download `plate_ocr.onnx` and its configuration.
Their source URLs and hashes are recorded in `ocr_provenance.json`.
The OCR model is not trained by this project. The ONNX file is excluded from Git.
