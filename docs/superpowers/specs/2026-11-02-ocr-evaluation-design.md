# OCR quality and credible portfolio evaluation

## Intent and scope

Improve complete Vietnamese plate readings and produce reproducible measurements suitable for a CV. Restore the existing private GitHub project to D:\ComputerVision\NhanDienBienSo; retain FastAPI, the web UI and the trained detector. Do not add parking features or claim field acceptance from development benchmarks.

## Approaches

1. More detector training: can improve localization but the existing detector already reports 99.11% mAP50 on 665 images; it does not solve the documented OCR weakness. Not the selected priority.
2. Improve OCR correctness and evaluation first: investigate the current BGR-to-RGB boundary, OCR candidate scoring and two-line processing; measure baseline and candidate on the same samples. The user explicitly selected this approach.
3. Replace the entire pipeline: substantial integration and training cost without evidence that replacement is needed; defer.

## Proposed implementation

- Recreate an isolated Python 3.12 environment and pinned runtime; download OCR weights with the existing checksums and public evaluation assets with revision/hash provenance.
- Freeze the shipped v1.3 code as baseline. Review upstream OCR input contracts before changing behavior. The current code passes OpenCV BGR arrays to an RGB OCR checkpoint; verify that this is an actual boundary mismatch using library source and a failing test.
- Acquire public transcribed Vietnamese plate images if available. Audit license/provenance, alphabet, duplicate pixels and plate identity across splits. Pretrained OCR training overlap may be unknown: say so; do not label it an unseen holdout.
- Keep development and final evaluation partitions separate by plate identity; never tune on final results. Use every eligible labeled example in the declared partition; publish excluded counts and exact rules. Existing 37 hand-labeled samples remain a legacy regression set, not a primary 100% accuracy claim.
- Compare baseline and candidate crop exact match, CER, per-condition results and uncertainty. Report full-pipeline accuracy only on data with valid full-image plate boxes/text; crop-only accuracy is never called end-to-end accuracy.
- Benchmark warm inference p50/p95 and throughput with hardware, batch, image size, sample count and timing scope. Measure API latency separately if included.
- Adopt an OCR change only when development results improve without clean regression, then evaluate the frozen candidate once on the final partition. If no change improves the metric, retain the baseline and publish the honest result. No guaranteed target accuracy.
- Adoption gate chosen by the implementer: primary metric is clean crop exact match on the development partition. Candidate must strictly improve exact-match count, must not increase aggregate CER, and must not reduce clean exact-match count on the legacy 37-sample regression set. Synthetic stress results are reported separately and cannot compensate for a clean regression. Correct contract fixes such as RGB alignment may be shipped with an explicit measured tradeoff if no metric winner exists; never describe that as an accuracy improvement.
- Add a concise model/evaluation card, runnable evaluation command and Vietnamese/English CV bullets tied to specific report files. Update README to identify the current measured version. Preserve historical experiment reports.

## Constraints and acceptance

- Use public data and local GPU only; no paid cloud jobs, publishing private data or changing repository visibility.
- No blanket character substitutions or ground-truth-dependent inference. Tests must catch color-order and confidence-alignment regressions.
- Each new nontrivial helper has a small runnable check. Existing API, temporal, camera and video contracts must still pass.
- Keep changes in a feature branch in the fresh checkout. Commit and push completed work as already requested; main integration follows final verification.
- Output includes baseline/candidate predictions, hashes, data partition manifest, metrics/denominators, latency report, reproducible setup, and CV wording whose numbers can be traced to the evidence.
- Runtime/data/history from the previous machine are not in Git and cannot be reconstructed by cloning. Do not claim old operational records were restored.

## Builder decisions

The implementer chooses the public dataset after inspection, exact deterministic split seed, modest candidate transformations and benchmark sample size. Record these choices before evaluation. Training OCR is conditional on available labeled data and development evidence, not required merely to claim training. Scope is one evaluated OCR/evaluation improvement, not an open-ended accuracy search or DOCX rewrite.
