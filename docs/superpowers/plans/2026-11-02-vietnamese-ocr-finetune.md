# Vietnamese OCR Fine-tuning Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, task by task; request a fresh whole-branch review before merge.

**Goal:** Train and fairly evaluate a Vietnamese OCR candidate, deploy it only if the predefined validation gate passes, and publish reproducible results plus an updated DOCX.

**Architecture:** Reuse VNLP parsing and FastPlateOCR CCT S v2; group data before splitting, fine-tune on a separate local CUDA environment, export to ONNX and compare against frozen release 1.4. Runtime integration follows validation selection; final test never selects model/settings.

**Tech Stack:** Python 3.12, Keras/PyTorch CUDA, FastPlateOCR 1.1.0, ONNX Runtime, OpenCV, unittest/Node, python-docx and document rendering.

**Spec:** docs/superpowers/specs/2026-11-02-vietnamese-ocr-finetune-design.md — explicitly approved for complete execution.

## Global Constraints

Public Vietnamese data, local RTX 3060 Laptop 6 GB, private GitHub unchanged, no paid/cloud resources, no parking expansion. Keep files inside NhanDienBienSo and preserve serving dependencies. Exclude all old 2000 benchmark IDs and legacy37 IDs/groups. New group split approximately80/10/10, fixed before training. At most30 epochs, patience6, seed recorded, LR1e-4, batch32 or16 for memory. Selection requires +0.5 percentage-point validation exact match, no aggregate CER or two-line regression, p95 no more than10% slower, and no legacy37 clean regression. No invented accuracy or real-camera claims.

## Review Focus

Transitive same-plate/source/crop links must not cross splits or reserved groups. Filename labels and source boxes are untrusted until archive/hash/shape checks pass. Region-head or layer mismatch must not silently turn fine-tuning into random initialization. Keras/ONNX and RGB/slot confidence must agree. Partially annotated scenes must not produce false full-scene precision claims.

## Task 1 — Frozen training data and environment

**Files:** create scripts/prepare_ocr_training.py, tests/test_ocr_training.py, requirements-ocr-train.txt and reports/ocr_finetune_manifest.json; extend .gitignore/.gitattributes only for new local artifacts/LF provenance. Reuse scripts.prepare_ocr_benchmark.parse_name/deduplicate and archive SHA.

**Interfaces:** build_groups(rows) returns source/plate/crop connected components; assign_splits(rows,reserved_plates,reserved_sources,seed) returns eligible rows with train/val/test or reserved exclusion. Manifest rows carry member, plate, bbox, square, split, group, pixel/source/image hashes and local image paths; CSV train/val uses image_path,plate_text. Validation/test have one deterministic sample per ID, train keeps unique captures.

- [x] Test transitive source links, reserved group propagation, deterministic split independent of input order, duplicate/conflicting crop labels and disjoint nonempty sets; observe failure before implementation.
- [x] Implement preparation with pinned archive checks, per-image bounds/decode checks, exclusion audit and refusal to overwrite a frozen manifest; run tests and the full preparation before inference/training. Record actual counts and manifest hash.
- [x] Create .venv-train using Python3.12; pin necessary Keras/PyTorch/export dependencies without modifying .venv. Verify a CUDA tensor and imports; do not install unrelated train extras unsupported on Windows.
- [x] Commit preparation, tests and frozen input evidence.

## Task 2 — Fine-tune with checkpoints and export

**Files:** create scripts/train_ocr.py and reports/ocr_finetune_training.json; training assets/checkpoints/logs under ignored models/training or runs/ocr_finetune. Test small pure training selection/gate helpers in tests/test_ocr_training.py.

**Interfaces:** official train CLI consumes prepared train/val CSVs only. Wrapper records initial assets/config hashes, fixed arguments, process/live status, epoch CSV and best/last checkpoint paths. Training report exposes selected checkpoint/hash and actual epochs/elapsed. Selected ONNX path feeds Task3; no test CSV passed to training.

- [x] Pin/download official Keras/config assets with hashes. Inspect loaded model weights/heads and execute a small CUDA forward/backward sanity check before the full run; fail on unintended weight mismatch or nonfinite loss.
- [x] Reuse official training CLI/callback behavior with declared seed/LR/batch/early stopping; save logs and recoverable best/last Keras checkpoints. Monitor real current logs and GPU, estimate timing from measured batches. Diagnose failures before making the one permitted validation-driven rerun.
- [x] Select best checkpoint by validation whole-plate accuracy, export to ONNX using supported backend, and assert decoded parity on validation examples. Record package versions and checksums; preserve logs rather than overwrite earlier experiments.
- [x] Commit training tooling, configuration and measured training evidence; keep source images/checkpoints out of Git until an adopted inference artifact is deliberately packaged.

## Task 3 — Validation selection and final comparison

**Files:** create scripts/evaluate_ocr_finetune.py and reports/ocr_finetune_validation.json / reports/ocr_finetune_test.json; extend tests/test_ocr_training.py for gate and annotated-target matching. Reuse summarize/edit distance and existing bbox IoU.

**Interfaces:** evaluate baseline frozen 1.4 and candidate single-pass/existing-variant paths through the same reading dictionary (plate,raw_text,ocr_confidence,valid_format,ocr_disagreement). Gate accepts validation summaries + legacy37 summaries; final evaluation receives the chosen frozen path/checkpoint only. Per-target matching is best IoU>=.5, missing detection is failure.

- [x] Test adoption rejects accuracy/CER/two-line/p95/legacy regressions; test full-image target metrics include missing detections, wrong text and unannotated extra boxes without claiming precision. Observe RED then implement.
- [x] Measure both candidate serving paths on new validation only; choose by the predefined gate and record all compared settings, including a rejected candidate. Run legacy37 and validation synthetic stress without using the final partition.
- [x] Request a pre-final review of split/training/evaluation correctness. Freeze chosen checkpoint/settings/code in Git before running final test once.
- [x] Publish paired crop exact/CER/Wilson/latency and annotated-target detection/end-to-end results, denominators and every prediction. Label old benchmark reruns as regression. Do not tune after final results.

## Task 4 — Verified release, CV and rendered DOCX

**Files:** only necessary active-model integration in recognition.py, scripts/download_ocr.py/models provenance/artifact, app.py/web metrics; extend existing contract tests. Update README.md, docs/CV.md, reports/OCR_BENCHMARK.md and scripts/build_report.py plus reports/Bao_cao_do_an_nhan_dien_bien_so.docx. Update report-only requirements if authoring needs it.

- [x] If gate passes, package selected ONNX/config with hashes and make the minimal active-model change while retaining rollback provenance. Otherwise retain1.4 and make the failed experiment clear. Verify fresh-setup assets and API fields/quality behavior.
- [x] Run full Python/Node checks and real API/video smoke; ensure displayed benchmark refers to the measured active model and no raw prediction arrays flood API responses.
- [x] Update measured model/data/training card and honest bilingual CV bullets. Build learning curves/results charts with standard plotting tools. Update DOCX theory/method/results/limitations; render every page, inspect layout and fix defects.
- [x] Review whole branch with a fresh reviewer, resolve important findings, commit/push, verify CI then merge/push main and verify its hash/CI. Preserve the approved spec and completion evidence.

Completion: product commit `958aa7e9e86cfd846ff4493887eca6ac33369411` merged/pushed to main; branch CI `41407032033` and main CI `41407229558` both succeeded. New final1855 crop exact1810/1855, CER64/14845, pipeline1720/1855; single mode was frozen before test. DOCX30pages rendered/reviewed; live API/UI/video and clean-package smoke passed. Detailed scope/checksums in `reports/ocr_finetune_release_validation.json`, publication evidence in `reports/ocr_finetune_publication.json`. Intermediate ignored clone/render folders retained after automatic deletion review returned blocked-by-policy; final delivery render is retained separately.

Self-review: all spec sections map to these four sequential deliverables; data and inference dictionary interfaces are shared explicitly. No additional user confirmation is needed for the implementation choices delegated in the approved design.
