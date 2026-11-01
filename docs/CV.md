# Mô tả dự án để đưa vào CV

**Biển Số Việt — Vietnamese License Plate Recognition**

Python · PyTorch · Ultralytics YOLO11n · OpenCV · ONNX Runtime · FastAPI · SQLite · JavaScript · GitHub Actions

## Tiếng Việt

- Xây dựng ứng dụng nhận diện biển số Việt Nam từ ảnh, camera và video, gồm API FastAPI, giao diện tra cứu, ROI, đồng thuận qua nhiều khung và lưu lịch sử SQLite.
- Fine-tune YOLO11n, đạt **99,11% mAP@50 / 87,50% mAP@50–95 trên 665 ảnh test** trong thí nghiệm detector trước đây; triển khai OCR CCT S v2 pretrained và xử lý biển hai dòng.
- Xây dựng benchmark OCR có thể tái lập trên **2.000 ID biển VNLP**, chia **379 dev / 1.621 test không trùng ID**; bản cuối đạt **96,55% exact match (1565/1621), CER 0,685%** trên crop test. OCR warmed CPU p50/p95 **60,1/110,2 ms**.

## English

- Built a Vietnamese license plate recognition application for images, camera streams and videos, with a FastAPI service, searchable SQLite history, ROI selection and temporal consensus.
- Fine-tuned YOLO11n, achieving **99.11% mAP@50 and 87.50% mAP@50–95 on 665 test images** in the earlier detector experiment; integrated pretrained CCT S v2 OCR with two-line plate processing.
- Developed a reproducible OCR benchmark with **2,000 VNLP plate identities**, split into **379 development / 1,621 test identities without overlap**. Achieved **96.55% crop-level exact match (1565/1621), 0.685% CER**, and warmed CPU OCR p50/p95 latency of **60.1/110.2 ms**.

## Khi trình bày hoặc phỏng vấn

Chọn 2–3 bullet phù hợp độ dài CV. Chỉ ghi phần công việc bạn thực sự đã thực hiện/hiểu và có thể trình diễn; điều chỉnh đại từ cho vai trò cá nhân. Không viết “tự train OCR”, “accuracy toàn hệ thống 99%”, “realtime 30 FPS nhận diện” hoặc “đạt chuẩn production” từ các số liệu này.

Exact match OCR đo trên crop có hộp đúng; detector mAP là phép đo khác, từ bộ dữ liệu/thí nghiệm trước. Chưa biết dữ liệu VNLP có trùng với pretrain của OCR hay không; nhãn filename chưa được kiểm tra độc lập và chưa có nghiệm thu camera triển khai ban đêm/mưa thật. Latency OCR không gồm detector, HTTP, trình duyệt hay lưu ảnh. Bản OCR được chọn trên dev, không chỉnh theo kết quả test; mức tăng nhỏ không tự chứng minh ý nghĩa thống kê.

Bằng chứng: [báo cáo OCR](../reports/OCR_BENCHMARK.md), [dự đoán và hash](../reports/ocr_benchmark.json), [manifest](../reports/ocr_benchmark_manifest.json), [detector training](../reports/training.json), [kiểm chứng video trước đây](../reports/RELEASE_VALIDATION.md). Repo giữ private theo cấu hình hiện tại; khi ứng tuyển, cấp quyền hoặc chuẩn bị demo phù hợp để người xem truy cập được bằng chứng.
