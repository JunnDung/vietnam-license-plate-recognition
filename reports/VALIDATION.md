# Kiểm chứng cập nhật chống mờ — 2026-10-06

## Huấn luyện và cách chọn model

- YOLO11n đã hoàn thành **40 epoch nền + 18 epoch fine-tune bổ sung**, trên RTX 3060 Laptop 6 GB. Lượt bổ sung gồm chuẩn bị dữ liệu và train mất 28.7 phút; không bao gồm các phép đánh giá sau train.
- Tập bổ sung: **3.189 ảnh gốc + 3.189 ảnh tăng cường**, gồm 1.914 ảnh mờ nhiều hướng (có một phần kết hợp tối), 638 ảnh thiếu sáng có nhiễu, 637 ảnh mưa/sương. Chỉ ảnh train được biến đổi; tất cả nhãn hình học giữ nguyên. Validation 674 ảnh và test 665 ảnh giữ nguyên.
- Seed tăng cường/train 73; AdamW, lr0 0.0003, lrf 0.1, input 640, batch 16, workers 2. Không lật ký tự; mosaic 0.2 và tắt ở 4 epoch cuối. Config đầy đủ và hash manifest trong `training.json`, `hardening.json`.
- Chọn `best` hoặc `last` bằng validation trước khi chạy test. Điều kiện: recall mờ tăng ≥3 điểm phần trăm; mAP50–95 ảnh gốc giảm ≤1.5 điểm; recall từng điều kiện giảm ≤1 điểm; precision từng điều kiện ≥95%. So sánh dùng cùng 200 ảnh validation, cùng threshold/IoU.
- Cả hai candidate đạt; recall mờ validation đều 226/226, `best` được chọn khi đồng hạng. mAP50–95 validation của `best` là 90.62%. Chi tiết mọi candidate trong `hardening.json`.
- **Giới hạn holdout:** kết quả test v1 đã được xem để chẩn đoán điểm yếu mờ. Test tái sử dụng lần này là benchmark hồi quy, không còn là dữ liệu chưa từng quan sát trong quá trình phát triển. Không dùng test chọn best/last hoặc ngưỡng trong lượt này. Vẫn cần dữ liệu độc lập theo camera/phiên quay.
- OCR CCT S v2 giữ pretrained; **không train/fine-tune OCR**.
- Model đang dùng: `models/plate_detector.pt`; SHA-256 `37a282619e923cc5715f81fe1f236e5c7fb281322d546f2aa3ae9a2de8ce49f6`. Health API trả hash của model nạp trong RAM; đã xác minh khớp báo cáo sau khi khởi động lại.

## Detector trên test gốc

| Chỉ số | V1 | Cập nhật |
|---|---:|---:|
| mAP@50 | 99.06% | 99.11% |
| mAP@50–95 | 87.74% | 87.50% |
| Precision tổng hợp | 97.80% | 97.96% |
| Recall tổng hợp | 97.86% | 98.11% |

Đánh giá đủ 665 ảnh, 796 biển. Precision/recall tổng hợp của Ultralytics dùng cách tổng hợp riêng; không đồng nhất với phép matching ở threshold 0.35 bên dưới.

## So sánh điều kiện khó trên cùng ảnh

Cùng 200 ảnh test, 230 biển có nhãn; confidence 0.35, matching đúng lớp duy nhất tại IoU ≥0.5. Ba điều kiện bổ sung được đo sau khi đã chốt model. Đây là biến đổi ảnh mô phỏng, không phải camera vật lý.

| Điều kiện mô phỏng | Recall V1 | Recall mới | Precision mới | Khớp mới |
|---|---:|---:|---:|---:|
| Ảnh gốc | 99.13% | 96.96% | 98.24% | 223/230 |
| Thiếu sáng | 98.26% | 96.96% | 97.81% | 223/230 |
| Mưa/sương | 99.13% | 97.39% | 98.68% | 224/230 |
| Mờ ngang 11 pixel | 80.43% | 97.39% | 97.82% | 224/230 |
| Thiếu sáng xám có nhiễu | 96.52% | 96.52% | 97.80% | 222/230 |
| Mờ chéo 11 pixel | 44.78% | 95.65% | 97.35% | 220/230 |
| Mưa và mờ ngang | 76.52% | 97.39% | 97.82% | 224/230 |

**Tradeoff đã quan sát:** mờ ngang cải thiện +16.96 điểm phần trăm, mờ chéo +50.87 điểm, mưa kèm mờ +20.87 điểm. Recall ảnh gốc/thiếu sáng/mưa đơn giảm nhẹ trên cohort này; không tuyên bố cải thiện mọi điều kiện. Không đổi model hay ngưỡng sau khi xem bảng test.

`robustness.json` giữ protocol bốn điều kiện cũ; `robustness_extended.json` giữ before/after bảy điều kiện. Thiếu sáng xám có nhiễu không mô phỏng phổ IR thật; mưa không mô phỏng giọt nước trên kính hoặc mọi phản xạ đèn. Các phép bổ sung này chỉ đánh giá detector.

## OCR và toàn quy trình

Dùng cùng 37 biển nguồn có thể đọc trong 40 ảnh chọn trước dự đoán. Phiên âm của trợ lý, có sửa nhãn sau lần kiểm tra sơ bộ; chưa được người khác kiểm tra độc lập. Ba mẫu nguồn quá mờ/che khuất giữ trong danh sách loại. Khi tạo điều kiện khó **không loại thêm mẫu nào**.

| Điều kiện | Crop OCR đúng cả biển | Pipeline V1 | Pipeline mới | CER crop |
|---|---:|---:|---:|---:|
| Ảnh gốc | 37/37 | 37/37 | 37/37 | 0.00% |
| Thiếu sáng | 37/37 | 37/37 | 37/37 | 0.00% |
| Mưa/sương | 37/37 | 37/37 | 37/37 | 0.00% |
| Mờ ngang 11 pixel | 3/37 | 2/37 | 3/37 | 75.16% |

**Mờ nặng vẫn yếu ở ký tự:** crop OCR chỉ đúng 3/37, pipeline mới đúng 3/37 (v1 2/37). Detector recall cao không khôi phục thông tin ký tự đã mất. Không công bố 100% nhận dạng dưới chuyển động. 37/37 ở ảnh gốc/tối/mưa chỉ là mẫu nhỏ có thiên lệch, không phải độ chính xác toàn dân số.

## Camera và kiểm tra phần mềm

- Browser so sánh 3 khung cách khoảng 33 ms; camera mục tiêu 5 lượt/giây, chỉnh 1–10. CLI giảm burst theo FPS file nguồn để giữ đủ mốc. Điểm Laplacian toàn ảnh là heuristic, có thể ưu tiên nền; không đảm bảo biển rõ. `--burst 1` tắt hoặc tăng số khung bằng `--burst`. Nếu mọi khung đều mờ cần chụp lại. Kiểm tra video và phép đo runtime mới trong [VIDEO_VALIDATION.md](VIDEO_VALIDATION.md).
- Crop nhỏ/thiếu sáng/ít chi tiết và bất đồng giữa các biến thể OCR bật `needs_review` dù điểm OCR cao. Các ngưỡng chỉ là heuristic cần hiệu chỉnh theo camera, không phải bộ phân loại mờ được hiệu chuẩn.
- Unittest cho corruption giữ hình học/tái lập, chọn khung rõ, quality/điểm OCR cao, bất đồng OCR, tiêu chí model và hợp đồng API/bãi xe: đạt. JavaScript kiểm tra chọn khung và hủy camera: đạt.
- API thật đã khởi động lại, hash model đang nạp khớp training/robustness/OCR; dữ liệu bãi xe trước đó được giữ.
- Video trống 7 giây: 3 lượt tại 0/3/6, không tạo biển giả. Video tổng hợp từ ảnh công khai với khung mờ/rõ: chọn khung rõ tại 0.2/3.2/6.2 và API đọc đúng `51A4032` cả ba lượt; vẫn đánh dấu bất đồng OCR. Đây là kiểm tra thuật toán/file video, không phải ghi hình camera thực.
- Workflow GitHub chạy unittest và JavaScript checks khi push; không tự train lại hoặc tạo benchmark.

## Phạm vi vận hành

Người dùng hiện chưa có camera USB/RTSP để thử. Chưa kiểm chứng ban đêm, mưa, IR, lóa, giọt nước trên kính, shutter, camera trình duyệt vật lý hay USB/RTSP dài hạn. Dataset chưa có camera/vehicle IDs nên có thể cùng biển ở nhiều split.

Bản hiện tại phục vụ thử nghiệm bãi xe có người xác nhận, phù hợp nhận diện khung rõ khi xe chậm/dừng. Chưa tự điều khiển barrier, tính phí, RFID hoặc xác định quyền nhận xe. Tham khảo [hướng dẫn camera](CAMERA_GUIDE.md) để hiệu chỉnh và tạo tập nghiệm thu độc lập. Báo cáo này giữ kết quả giai đoạn chống mờ; DOCX mới và RELEASE_VALIDATION.md tổng hợp phiên bản 1.3.0, giao diện đã bỏ phần bãi xe.
