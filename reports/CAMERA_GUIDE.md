# Kiểm tra camera tại cổng bãi xe

Đây là hướng dẫn hiệu chỉnh và nghiệm thu; dự án chưa được thử bằng camera đêm/mưa thật. Các phép đo mô phỏng nằm trong `robustness.json` và `ocr_weather.json`. Mờ mạnh có thể xóa thông tin ký tự: model phát hiện được hộp vẫn có thể đọc sai cả biển.

## Giảm mờ ngay khi ghi hình

1. Chọn vị trí xe chậm hoặc dừng để xác nhận. Lấy nét ở khoảng cách biển xuất hiện, tránh chụp quá rộng làm biển chỉ còn vài chục pixel.
2. Thử giới hạn thời gian phơi sáng theo tốc độ xe và góc nhìn. Với camera LPC, tài liệu Axis thường dùng giới hạn 1/500 giây hoặc ngắn hơn; đây là điểm bắt đầu thử, không phải thông số đã được chứng nhận cho model này. Tăng tốc màn trập có thể làm ảnh tối hơn, nên thử đồng thời ánh sáng hỗ trợ và gain.
3. Ban đêm, kiểm tra đèn hỗ trợ/IR, biển phản quang, lóa từ đèn xe và độ nét ký tự, thay vì chỉ nhìn độ sáng toàn khung. Chế độ IR trắng đen cũng cần dữ liệu đánh giá riêng.
4. Khi trời mưa, kiểm tra giọt nước và bụi trên kính, vị trí che mưa và ánh sáng phản xạ. Rain/fog overlay trong phép đo không mô phỏng được mọi ảnh hưởng này.
5. Thử WDR theo hướng dẫn camera. Tài liệu LPC của Axis đề nghị tắt WDR hoặc dùng kỹ thuật tránh artefact chuyển động; không áp dụng máy móc cho mọi hãng/mọi chế độ.

Nguồn về màn trập, ánh sáng và WDR: [Axis License Plate Capture](https://whitepapers.axis.com/en-us/license-plate-capture). Đây là tài liệu ghi hình, không phải benchmark cho dự án.

## Chọn khung và cảnh báo trong ứng dụng

- Camera trình duyệt lấy 3 khung cách khoảng 33 ms và chọn khung có điểm chi tiết cao hơn; nhận diện mặc định mục tiêu 5 lượt/giây, chỉnh 1–10. Hình xem trực tiếp yêu cầu 30 FPS, độc lập với khung đã phân tích; tốc độ thực được hiển thị và phụ thuộc camera/máy. CLI có `--fps 5`, tối đa burst 3 khung và giảm burst theo FPS file nguồn; `--burst 1` tắt lựa chọn, `--burst 5` tăng số khung. Số khung lớn hơn làm tăng độ trễ và có thể bỏ qua xe đi nhanh. Chưa xác nhận FPS bằng camera vật lý.
- Điểm chọn khung là phương sai Laplacian sau giảm kích thước và làm mượt. Điểm tính trên cả ảnh, có thể ưu tiên nền nhiều cạnh hoặc nhiễu; không bảo đảm biển số rõ. Chưa có ROI được hiệu chỉnh theo cổng hoặc tracking từng xe.
- API trả `quality.brightness`, `quality.detail_score`, `quality.issues` cho từng crop. `low_light`, `low_detail`, `small_plate` hoặc `ocr_disagreement=true` bật `needs_review`, kể cả OCR trả điểm cao. Điểm OCR không phải xác suất đúng đã được hiệu chuẩn.
- `PLATE_MIN_DETAIL=25` và `PLATE_MIN_BRIGHTNESS=40` là ngưỡng heuristic mặc định. Hiệu chỉnh trên ảnh của chính camera, khởi động lại server để áp dụng; ngưỡng này không được đo như một bộ phân loại mờ chính xác. Cảnh báo không chặn người vận hành đối chiếu và sửa biển số.
- Nếu cả 3 khung đều mờ, lựa chọn khung không khôi phục được ký tự đã mất. Yêu cầu xe dừng/chụp lại và vẫn xác nhận ảnh trước khi ghi nhận vào/ra.

## Tập nghiệm thu độc lập

Thu ảnh/video của chính cổng, có biển dài, biển vuông, xe máy, xe không có biển trong khung, biển nhỏ, lóa, che khuất; chia theo camera và phiên quay trước khi train. Ghi nhận ngày/đêm/mưa, tốc độ và lỗi luồng camera. Không đặt ảnh gần nhau từ cùng lượt xe ở cả train và test.

Người gán nhãn kiểm tra độc lập hộp và chuỗi ký tự. Giữ lại cả mẫu khó hoặc không thể đọc; không loại chúng rồi công bố tỷ lệ đúng chung. Đo riêng:

- Recall/precision detector và tỷ lệ đọc đúng **cả biển** trên toàn bộ mục tiêu.
- Tỷ lệ xác nhận nhầm, bỏ sót, chụp lại và sửa OCR trong luồng bãi xe.
- Latency p50/p95, độ trễ từ camera đến ảnh, xe bị bỏ qua do chu kỳ lấy mẫu và độ bền khi chạy nhiều giờ.

Chủ bãi đặt ngưỡng chấp nhận theo quy trình vận hành. Bản hiện tại hỗ trợ thử nghiệm có người xác nhận, chưa tự điều khiển barrier hay chứng minh quyền nhận xe.
