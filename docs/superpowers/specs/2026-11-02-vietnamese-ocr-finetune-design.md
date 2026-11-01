# Vietnamese OCR fine-tuning and measurable release quality

## Intent and existing authorization

The user asks to continue improving the project and its measured results, retaining their previous priority: OCR and trustworthy evaluation for a portfolio. Use Vietnamese plates, public data and the local RTX 3060 Laptop 6 GB. Continue in D:\ComputerVision\NhanDienBienSo; retain private GitHub visibility and publish verified changes as previously authorized. No paid/cloud training or parking expansion.

Current baseline is release 1.4.0 / commit 8f03947: pretrained CCT S v2 with RGB/slot alignment, multiple preprocessing variants and conditional rectification. Published VNLP crop test: 1565/1621 exact match (96.55%), CER 89/12990 (0.685%), two-line exact match 701/742 (94.47%); CPU p95 110.16 ms. Heavy simulated blur remains weak. These are development benchmark results, not physical-camera acceptance.

## Approaches and recommendation

1. Continue adding preprocessing: last iteration gained only 3/1621 correct readings while increasing p95. Further variants risk slower inference and benchmark overfitting.
2. Fine-tune the existing OCR on Vietnamese plate crops, select only on a new development set, then export and compare: recommended continuation of the user's selected OCR priority. Official CCT S v2 Keras checkpoint and training/export interfaces are available. This can address two-line layouts and potentially reduce inference variants; improvement is not guaranteed.
3. Only optimize runtime or extend evaluation: useful supporting work but does not address the remaining recognition errors. Do this where necessary to validate the fine-tuned candidate, rather than replace the OCR objective.

The implementer recommends option 2 with bounded experiments and explicit adoption criteria. The user has already selected the broader OCR/evaluation priority; the new training/release scope below requires design approval before implementation.

## Data and evaluation isolation

- Reuse the original VNLP archive with SHA-256 f9da66c4cb443375ff40be140628ccfb3dc35f22755d82e341299e05b07a4a21. Reuse validated filename parsing, box convention and hashing helpers; do not download another copy unnecessarily.
- Exclude every plate ID in the existing 2000-ID benchmark and the legacy 37-image regression set from new training, validation and final test. Exclude connected images sharing a source-pixel identity with these reserved plates. The old benchmark remains a disclosed regression benchmark, not the new selection set.
- Group remaining examples by connected plate ID and exact source/crop pixel identity. Split groups deterministically, approximately 80% train / 10% validation / 10% final test, with a new recorded seed. Freeze actual counts, image/source/checkpoint hashes, exclusions and split manifest before training or prediction. No camera/session isolation is claimed where metadata is absent.
- Train on available unique crops of training IDs. Validation/test use one deterministic source crop per plate ID to prevent repeated observations inflating the denominator. Do not remove samples or correct labels in response to predictions. Invalid boxes, unreadable files or unsupported alphabet/length are handled before inference with recorded reasons; do not exclude labels simply because the model finds them difficult.
- Filename labels may contain noise and have not been independently audited; upstream pretrained overlap is unknown. New separation establishes isolation from this project's fine-tuning, not proof that OCR pretraining never saw the source.

## Model training and reproducibility

- Start from the official cct_s_v2_global.keras and matching architecture/plate configuration; record URLs and SHA-256 before use. Reuse fast-plate-ocr 1.1.0 rather than implement a separate OCR architecture.
- Create an isolated project-local training environment so runtime/API dependencies remain unchanged. Use Keras with its supported PyTorch CUDA backend; install only necessary training/export dependencies and pin the working versions. Keep the serving API on the existing environment/model while experimenting.
- Predeclare an initial bounded run: seed recorded, AdamW, initial learning rate 1e-4, batch 32 (reduce to 16 if memory requires), at most 30 epochs, early stopping on validation whole-plate accuracy with patience 6. Save best and last resumable checkpoints, epoch CSV, configuration and live status. Estimate completion time from actual throughput, not a prior promise.
- No character mirroring or text substitutions. Use moderate affine/color/noise/blur augmentation with fixed recorded settings; synthetic night/rain/blur tests remain explicitly synthetic. Do not train on final-test images or tune corruption settings using their results.
- Verify pretrained weights actually load; document any deliberately excluded region head. A second run is allowed only for a diagnosed training failure or one documented validation-driven revision, not an unlimited search. Test remains unopened for model selection.

## Selection, export and measurements

- Compare baseline 1.4 with the chosen checkpoint on new validation data. At most two serving paths: fine-tuned single-crop inference, and the existing preprocessing path with the fine-tuned weights. Choose using validation only; do not introduce a text-guessing fallback.
- Adoption gate: validation exact match improves by at least 0.5 percentage points over baseline; aggregate CER and two-line exact match do not regress; warmed CPU crop p95 is no more than 10% slower than baseline; legacy 37 clean crop and pipeline exact-match counts do not decline. If no candidate meets the gate, retain the active model and publish the candidate's measured results and failure reasons.
- Export the selected Keras checkpoint to ONNX; verify decoded predictions against Keras on validation examples and record numerical/export differences. Keep the pretrained checkpoint available for baseline comparison and rollback. Deploy trained weights/config/provenance reproducibly from the repo or an authorized GitHub artifact, without requiring private runtime/history data.
- Freeze candidate code, checkpoint and settings before evaluating the new final partition once. Publish total and one-/two-line exact match, CER, Wilson 95% intervals, all per-sample predictions, paired improvements/regressions and relevant paired significance evidence. Existing 1621 test images may be rerun only as explicitly labeled regression, never the new holdout claim.
- Measure full-image annotated-target detection success and annotated-target detection-plus-correct-reading success at IoU >= 0.5 on data with valid source boxes/text. Do not label this as full-scene precision: other plates may be unannotated. Include every selected target and detection failures in the denominator.
- Report warmed crop and pipeline latency p50/p95 with hardware, device, batch and timing scope. Crop throughput, source video FPS, preview FPS and actual API processing rate remain distinct. Record synthetic stress failures as well as gains; do not promise real-night/rain quality without camera evidence.

## Release and documentation

Preserve existing image/camera/video/history/temporal API contracts and the current review/quality behavior. Make only integration changes needed by the selected model. Test data boundaries, split isolation, model input/output/export contracts, new metrics and existing Python/Node workflows; verify real API and video smoke behavior. Review the complete change before merging, push GitHub and verify CI/remote hashes.

Update README, model/evaluation card, Vietnamese/English CV bullets and the existing capstone DOCX with the actual model/data/training theory, learning curves, measured results and limitations. Render and inspect the DOCX before delivery. No headline 99% or 100% claim unless the specified numerator/denominator actually support it; no blending detector mAP with OCR accuracy or hiding rejected/reviewed cases.

## Builder decisions and limits

The implementer chooses exact split seed/counts after the source audit, compatible pinned training packages, moderate augmentation parameters, export fallback if needed, and whether either serving path passes the stated gate. These are implementation choices, not additional user approvals. Local checkpoint recovery, routine fixes and GitHub publication stay authorized throughout the run. Material scope changes, paid resources or publishing private data require separate instruction.

References: [official training CLI](https://ankandrew.github.io/fast-plate-ocr/latest/training/cli/train/), [official model assets](https://github.com/ankandrew/fast-plate-ocr/releases/tag/arg-plates), [VNLP authors](https://github.com/fict-labs/VNLP). Dataset redistribution rights remain unconfirmed; source images stay outside Git.
