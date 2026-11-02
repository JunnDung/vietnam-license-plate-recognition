`plate_detector.pt` is the YOLO11n checkpoint fine-tuned locally by `scripts/train.py`.
Its hash and held-out test metrics are in `reports/training.json`.

Active OCR is CCT S v2 from [fast-plate-ocr](https://github.com/ankandrew/fast-plate-ocr),
fine-tuned in this project on 26,939 Vietnamese crops. `plate_ocr_vn.onnx` and
`plate_ocr_vn_config.yaml` are included in Git; their hashes, upstream initialization
and training provenance are in `ocr_vn_provenance.json`. Serving uses one RGB crop.
See `reports/OCR_FINETUNE.md` for split isolation, selection, metrics and limitations.

`python scripts/download_ocr.py` downloads the frozen pretrained baseline as
`plate_ocr.onnx` / `plate_ocr_config.yaml`. Its separate `ocr_provenance.json`
remains valid for comparison and rollback. It does not replace the active fine-tuned files.
Source dataset images and resumable training checkpoints are excluded from Git.
