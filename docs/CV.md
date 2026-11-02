# Mô tả dự án để đưa vào CV

**Biển Số Việt — Vietnamese License Plate Recognition · GitHub (Private)**

Python · Keras/PyTorch · Ultralytics YOLO11n · OpenCV · ONNX Runtime · FastAPI · SQLite · JavaScript · GitHub Actions

## Tiếng Việt

- Xây dựng ứng dụng nhận diện biển số Việt Nam từ ảnh, camera và video, gồm API FastAPI, giao diện tra cứu, ROI, đồng thuận qua nhiều khung và lưu lịch sử SQLite.
- Fine-tune CCT S v2 OCR trên **26.939 crop / 15.123 ID biển**; đánh giá trên **1.855 ID test tách biệt với train/validation của lần fine-tune**, đạt **97,57% crop exact match, CER 0,431%**. Giảm OCR CPU p95 từ **109,0 xuống 30,7 ms** so với baseline trên cùng tập test.
- Fine-tune YOLO11n đạt **99,11% mAP@50 / 87,50% mAP@50–95 trên 665 ảnh test** ở thí nghiệm detector trước; pipeline với OCR mới phát hiện và đọc đúng **1720/1855 mục tiêu có nhãn (92,72%)** trong phép đo ảnh nguồn mới.

## English

- Built a Vietnamese license plate recognition application for images, camera streams and videos, with a FastAPI service, searchable SQLite history, ROI selection and temporal consensus.
- Fine-tuned CCT S v2 OCR on **26,939 crops / 15,123 plate identities**; achieved **97.57% crop-level exact match and 0.431% CER on 1,855 test identities disjoint from this fine-tuning run's training/validation sets**. Reduced warmed CPU OCR p95 latency from **109.0 to 30.7 ms** versus the paired baseline.
- Fine-tuned YOLO11n to **99.11% mAP@50 / 87.50% mAP@50–95 on 665 test images** in the earlier detector experiment; the updated detector-plus-OCR pipeline correctly detected and read **1,720/1,855 annotated targets (92.72%)** in the new source-image evaluation.

## Khi trình bày hoặc phỏng vấn

Chọn 2–3 bullet phù hợp độ dài CV, chỉ ghi phần bạn thực sự hiểu và có thể trình diễn. Đây là fine-tune kiến trúc/trọng số có sẵn, không phải tự đề xuất một kiến trúc OCR mới. Có thể giải thích loss cross-entropy theo 10 slot, RGB, tách ID/pixel trước train, chọn bằng validation và export ONNX có kiểm chứng.

Baseline cùng test đạt 1792/1855 = 96,60%; candidate đạt 1810/1855 = 97,57%, tăng ròng **18 mẫu / 0,97 điểm phần trăm**. Sửa đúng 23 và làm sai thêm 5, exact McNemar hai phía p = 0,000912 với giả định độc lập giữa mục tiêu; Wilson 95% candidate **96,77–98,18%**. Biển hai dòng đạt 801/833 = 96,16%, so với 784/833 = 94,12%. Checkpoint và single-pass đã khóa ở `bf26eb6` trước test. Validation 98,47% không phải điểm test cuối.

Crop exact match khác detector mAP và khác pipeline. Pipeline chỉ đo mục tiêu đã có nhãn IoU ≥0,5, không phải precision mọi biển trong cảnh. Chưa xác minh mức trùng VNLP với pretrained OCR hoặc bộ train detector cũ; nhãn filename chưa được người kiểm tra độc lập toàn bộ, và chưa có nghiệm thu camera triển khai. Các giới hạn này cần giữ khi giải thích phạm vi holdout.

Độ trễ dùng ONNX CPU hai luồng, cùng máy Ryzen 7 6800H; pipeline dùng detector CUDA RTX 3060 Laptop. OCR latency không gồm detector/IO/HTTP/lưu ảnh, không tương đương FPS camera. Model chưa xử lý tốt mờ mạnh: 104/200 validation mô phỏng, baseline 106/200. Không viết “accuracy toàn hệ thống 99%”, “30 FPS nhận diện”, “đạt chuẩn production” hoặc “đã giải quyết mọi cảnh đêm/mưa”.

Bằng chứng: [phương pháp và kết quả mới](../reports/OCR_FINETUNE.md), [test từng mẫu và hash](../reports/ocr_finetune_test.json), [manifest](../reports/ocr_finetune_manifest.json), [training/log](../reports/ocr_finetune_training.json), [detector trước đây](../reports/training.json), [DOCX đồ án](../reports/Bao_cao_do_an_nhan_dien_bien_so.docx). Repo giữ private; khi ứng tuyển, cấp quyền phù hợp hoặc chuẩn bị demo để người xem kiểm tra bằng chứng.
