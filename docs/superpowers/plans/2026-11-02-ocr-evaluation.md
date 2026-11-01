# OCR quality implementation plan

> For agentic workers: use superpowers:executing-plans inline, then request a fresh whole-branch review.

**Goal:** Improve OCR correctness and publish defensible, reproducible CV metrics.
**Architecture:** Keep the shipped detector and FastPlateOCR checkpoint; fix measured inference boundaries and compare baseline/candidate with a deterministic plate-disjoint evaluation manifest.
**Tech stack:** Python 3.12, OpenCV, ONNX Runtime, PyTorch CUDA, FastAPI, unittest and existing Node checks.
**Spec:** docs/superpowers/specs/2026-11-02-ocr-evaluation-design.md

## Global constraints

Public data, local GPU, private repo unchanged; no guaranteed score, no character guessing. Fresh clone is the isolated workspace; use a feature branch there without creating another checkout. Preserve old reports and all existing API fields. Runtime/data from the old machine are absent.

## Review focus

RGB channel order; confidence after normalization/padding; duplicated identity or conflicting labels; path traversal in downloads/extraction; accidental evaluation-set tuning. Pin each in tests/protocol below.

## Task 1 Restore baseline and freeze evaluation inputs

- [x] Create feature branch in the fresh clone; recreate .venv and download verified OCR weights; save git-show baseline recognition module locally.
- [x] Run all existing Python/Node contracts and record failures before changes.
- [x] Inspect public transcribed datasets, record source revision/license and deterministic identity-disjoint dev/test rules before measuring predictions. If crop dataset is unavailable, use the explicitly labeled legacy regression set and publish the coverage limitation rather than fabricate a larger result.
- [x] Add tests in tests/test_ocr_evaluation.py for split isolation, duplicate/conflicting-label behavior and metrics; watch RED, then implement scripts/prepare_ocr_benchmark.py and scripts/benchmark_ocr.py only as required by inspected data.
- [x] Commit the reproducible evaluation workflow.

## Task 2 Correct OCR input and scoring

- [x] Add tests/test_ocr_contract.py that sends a colored crop through PlateEngine.read_crop and verifies the OCR receives RGB for every variant; test padded/spaced prediction probabilities remain aligned with retained characters. Confirm failure on shipped code.
- [x] Make minimal recognition.py correction; preserve explicit disagreement and quality flags. Run existing contracts and new tests.
- [x] Measure baseline vs candidate on development samples; adopt by the design gate. Freeze chosen code/config before final evaluation; report failures as well as gains.
- [x] Commit OCR correction and evidence.

## Task 3 Measure and publish portfolio evidence

- [ ] Evaluate the frozen candidate once on final partition, publish denominators, exact match, CER, Wilson interval, paired changes and per-sample outputs; state pretrained overlap unknown.
- [ ] Benchmark warm crop OCR p50/p95 and latency scope; preserve detector metrics as historical detection-only results. Test CLI against invalid manifests and empty selections.
- [ ] Update README and docs/CV.md with measured Vietnamese/English bullets, reproducible commands, limitations and data/model cards. Re-run Python/Node contracts and review whole branch with fresh reviewer.
- [ ] Fix important reviewed issues with regression checks; commit/push and verify remote hash and CI. Merge only after checks pass, as authorized.
