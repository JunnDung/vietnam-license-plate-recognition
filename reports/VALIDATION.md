# Kiểm chứng bản train cuối — 2026-10-06

## Mô hình và dữ liệu

- YOLO11n fine-tune **40 epoch**, ảnh 640 px, batch 16, seed 42 trên **NVIDIA GeForce RTX 3060 Laptop GPU**. Lượt train chính và test mất 29.9 phút; lượt warmup trước đó không tính trong thời gian này.
- 3.189 ảnh train / 674 validation / **665 test**. Loại 44 ảnh trùng pixel và 6 nhãn lỗi. Manifest, revision và hash archive: [dataset.json](dataset.json).
- Checkpoint tốt nhất chọn trên validation, sau đó đánh giá test. Không dùng test để chọn checkpoint của lượt train này.
- mAP@50 **99.06%**, mAP@50–95 **87.74%**, precision **97.80%**, recall **97.86%**. Đây là phát hiện vùng biển số, không phải độ chính xác ký tự.
- Model: `models/plate_detector.pt`; SHA-256 `d8ead0e764779930aab6325848190852ed6594cce84b82faa01bfeed94f3b87e`. Cả báo cáo OCR và robustness dùng cùng hash này.
- OCR CCT S v2 là pretrained, **không fine-tune OCR**. Nguồn và checksum: `models/ocr_provenance.json`.

## Đọc ký tự

Chọn 40 ảnh test bằng seed 77 trước khi dự đoán, lấy biển số đầu tiên mỗi ảnh. Phiên âm bằng mắt bởi trợ lý; loại 3 ảnh quá mờ/che khuất. Một số nhãn được sửa sau khi phóng to trong lượt kiểm tra sơ bộ; ghi chú audit giữ nguyên trong JSON. **Chưa được người khác kiểm tra nhãn độc lập.**

Trên **37 biển có thể đọc**: crop OCR đúng cả biển **100.00%**, quy trình phát hiện + OCR đúng biển được chọn **100.00%**, CER crop **0.00%**. Trung bình **223.4 ms** trên CPU cho cả đọc crop có nhãn lẫn chạy pipeline, không phải latency API riêng. Chi tiết từng mẫu: [ocr_evaluation.json](ocr_evaluation.json).

Mẫu nhỏ và có loại ảnh không đọc được; các tỷ lệ này không đại diện mọi camera hoặc mọi biển số trong ảnh.

## Điều kiện khó mô phỏng

Cùng 200 ảnh test, 230 biển có nhãn; confidence 0.35, IoU >= 0.5 và đúng lớp. Không thay đổi model sau khi xem kết quả này.

| Điều kiện | Biển khớp | Recall | Precision |
|---|---:|---:|---:|
| original | 228/230 | 99.13% | 97.85% |
| synthetic_dark | 226/230 | 98.26% | 97.41% |
| synthetic_rain_fog | 228/230 | 99.13% | 98.70% |
| synthetic_motion_blur | 185/230 | 80.43% | 97.88% |

Thiếu sáng và mưa/sương ở đây là biến đổi ảnh, **không phải camera đêm/mưa thực tế**. Mờ chuyển động còn yếu: recall chỉ 80.43%. Tại cổng nên lấy khung hình khi xe chậm/dừng và biển rõ; cần kiểm chứng tốc độ màn trập, ánh sáng và góc đặt camera thực tế.

## Phần mềm đã chạy kiểm tra

- Contract checks: upload lỗi/quá lớn, API key, save=false, tìm kiếm, CSV, xóa; xác nhận biển số sửa OCR, xe vào trùng, xe ra không có lượt vào, giữ ảnh bằng chứng và hai yêu cầu vào đồng thời. Đều pass.
- Python compile, `pip check`, cú pháp JavaScript và PowerShell setup: pass.
- API thật đã nạp model cuối; ảnh công khai đọc được biển `51A4032`, đồng thời đánh dấu biển nhỏ có OCR thấp để kiểm tra. Không kết luận đúng cho biển nhỏ này.
- CLI video 7 giây gửi 3 khung hình ở giây 0/3/6 đến API thật, video trống trả không có biển. USB/RTSP vật lý và quyền camera trình duyệt **chưa thử trên thiết bị thực**.
- Giao diện đã thực hiện xác nhận xe vào, xem trong bãi, đối chiếu ảnh xe ra, xác nhận ra và tra cứu lượt đã đóng. Bộ đếm trở về 0 xe; ảnh vào/ra được giữ. Ảnh minh chứng: [parking-closed.jpg](parking-closed.jpg), [parking-comparison.jpg](parking-comparison.jpg).

## Phạm vi ứng dụng

Bản thử nghiệm bãi xe với người vận hành xác nhận, API xử lý ảnh và kho tra cứu cục bộ. Chưa có tính phí, barrier, RFID hoặc nhận diện chủ xe. Dataset không có camera/vehicle IDs, nhãn thời tiết hoặc đầy đủ nhãn ký tự; vẫn có khả năng cùng biển ở nhiều split. Cần một tập đánh giá độc lập theo camera/phiên quay, đủ ngày/đêm/mưa và ảnh không có biển trước khi vận hành bãi xe thật.
