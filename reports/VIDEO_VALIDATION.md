# Nhận diện video và tăng tần suất camera — 2026-10-06

Ghi chú phạm vi giao diện: phần bãi giữ xe và xác nhận vào/ra đã tạm bỏ ở bản cập nhật tiếp theo cùng ngày; nhận diện ảnh/video/camera và tra cứu vẫn hoạt động. Dữ liệu/API bãi xe cũ được giữ, các mô tả luồng xác nhận bên dưới là phạm vi của phiên bản khi đo video.

## Cách sử dụng

Ở tab **Nhận diện**, chọn file video MP4/WebM/OGV mà trình duyệt đọc được (tối đa 500 MB, 10 phút), chọn số khung phân tích mỗi giây video rồi bấm **Phân tích video**. Mặc định 5 khung/giây: video 4 giây tạo 20 mốc lấy mẫu 0.00, 0.20, …, 3.80. Mỗi khung được xử lý tuần tự qua `/api/recognize`; file gốc không được upload. Khung gửi đi có cạnh dài tối đa 1280 px, detector vẫn dùng input 640 FP32 và OCR không đổi.

Có tạm dừng/tiếp tục, quét lại, tiến độ, bảng biển số theo mốc giây và nút xem lại khung với hộp nhận diện. CSV chứa tất cả kết quả; giao diện giữ 100 dòng gần nhất để không làm nặng trang. Có thể cùng biển xuất hiện ở nhiều dòng, không dùng số dòng làm số xe. Không bổ sung tracking hoặc gộp xe vì chưa có dữ liệu video gán nhãn để kiểm chứng.

Video mặc định không lưu lịch sử. Bật lưu nếu cần ảnh bằng chứng cho luồng xác nhận vào/ra; mỗi khung có biển sẽ tạo bản ghi riêng, không tự tạo lượt gửi. `created_at` trong lịch sử là thời điểm xử lý, còn mốc giây video nằm trong source và CSV. Tạm dừng không hủy lượt API đã gửi: lượt đó có thể được lưu nếu đã chọn lưu, nhưng phản hồi sau khi dừng không cập nhật hình hoặc bảng kết quả; khung chưa hoàn thành sẽ được thử lại khi tiếp tục.

Camera trình duyệt yêu cầu hình xem trực tiếp 30 FPS, còn tốc độ nhận diện mục tiêu mặc định 5 lượt/giây, chỉnh 1/2/5/10. Lấy khung rõ hơn trong 3 khung cách khoảng 33 ms. Một yêu cầu tại một thời điểm; thời gian chờ chỉ bù phần còn lại của chu kỳ mục tiêu, không chờ thêm 3 giây sau xử lý. Hình trực tiếp và khung đã phân tích được hiển thị riêng; hộp là kết quả của khung đã phân tích, không phải tracking thời gian thực trên hình trực tiếp. UI hiển thị FPS camera cung cấp và tốc độ nhận diện thực đạt.

CLI `scripts/camera.py --source D:\video.mp4 --fps 5` đọc video bằng OpenCV và xuất JSON từng dòng với `video_time`, `processing_ms`. Có `--fps 1` đến `--fps 10`, `--interval 3` để giữ cách lấy mẫu cũ. Burst tự giảm theo FPS video nguồn để không ăn mất mốc lấy mẫu. CLI hỗ trợ video dài hoặc codec browser không đọc được; thông số FPS/buffer với USB/RTSP có thể bị driver bỏ qua.

## Hiệu năng đã đo

API mặc định chọn CUDA khi `torch.cuda.is_available()`, dùng CPU nếu không có CUDA. `PLATE_DEVICE=cpu` ép CPU. Health của server hiện chạy xác nhận device `0` và hash detector `37a282619e923cc5715f81fe1f236e5c7fb281322d546f2aa3ae9a2de8ce49f6`. Không thay trọng số, giảm input detector, bỏ biến thể OCR hoặc đổi FP16 để tăng tốc.

37 ảnh nguồn công khai đã có nhãn OCR, ba lượt warmup, đo trực tiếp `PlateEngine.predict` trên RTX 3060 Laptop 6 GB; OCR CPU. Đây là mẫu nhỏ đã chọn đọc được, không phải video camera độc lập. Kết quả đầy đủ trong `video_performance.json`.

| Runtime detector | Trung bình | p50 | p95 | Nghịch đảo thời gian trung bình | Đọc đúng mẫu |
|---|---:|---:|---:|---:|---:|
| CPU | 141.46 ms | 131.12 ms | 228.71 ms | 7.07 lượt/s | 37/37 |
| CUDA FP32 | 107.92 ms | 100.13 ms | 191.21 ms | 9.27 lượt/s | 37/37 |

Các số này **chưa gồm** lấy/giải mã video, burst, JPEG, HTTP hoặc lưu ảnh. Không dùng 9.27 làm cam kết FPS camera. Mục tiêu 10 có thể không đạt, đặc biệt nhiều biển trong cùng khung. Lần chạy đầu có khởi tạo GPU và thường chậm hơn; UI không xếp hàng để đuổi theo FPS yêu cầu.

## Kiểm chứng chức năng

- Video WebM VP8 tổng hợp 4 giây, nguồn 10 FPS, 640×480: giây 0–1 và 3–4 là ảnh trống; giây 1–3 là ảnh công khai biển `51F44614`. Đây là video từ ảnh tĩnh, không có chuyển động thật.
- Browser + API GPU thật: lấy đủ 20 khung tại mức 5 khung/giây video; có đúng 10 dòng `51F44614` tại 1.00–2.80, không có biển giả trong các khung trống. Lượt đầu quan sát 6.7 lượt/s, lượt tiếp tục đã warmup 10.4 lượt/s trên video có một nửa khung trống (không phải camera FPS). Ảnh giao diện trong `video-interface.png`.
- CSV thực được tải xuống và kiểm tra: 10 dòng dữ liệu, đúng mốc giây/biển; không bật lưu nên các lượt không ghi vào lịch sử. Nút xem khung tại 2.00 giây hiển thị đúng ảnh và bbox.
- Tạm dừng ngay khi đang xử lý: hiện **Tiếp tục**, không nhận thêm dòng phản hồi cũ; tiếp tục quét từ mốc chưa hoàn thành. Đổi tab/rời trang dừng luồng; đổi nguồn thu hồi object URL.
- Node checks: chọn khung rõ/cancellation, resize giới hạn 1280, thời gian bù FPS; lấy mẫu video đúng mốc, không lưu ngầm, không chồng yêu cầu, pause/replay khi đổi FPS. CI chạy các checks này.
- CLI + API thật: video trống 7 giây nguồn 5 FPS; `--interval 3` tạo 3 lượt, mặc định 5 FPS tạo đủ 35 lượt với mốc đúng, không có biển giả. API/SQLite/bãi xe và kiểm tra chống mờ hiện có đều đạt.

Chưa có camera vật lý USB/RTSP, nên chưa đo hình trực tiếp 30 FPS, độ trễ từ camera, mất khung, chạy nhiều giờ hoặc điều kiện đêm/mưa thật. Video thật có xe di chuyển và nhãn từng khung vẫn cần để nghiệm thu. Giới hạn OCR mờ mạnh 3/37 của báo cáo chống mờ vẫn giữ nguyên; tăng FPS không khôi phục chữ đã mất.
