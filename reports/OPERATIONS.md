# Vận hành nhận diện biển số phiên bản 1.3.0

## Khởi động trên máy hiện tại

Thư mục làm việc: `D:\ComputerVision\NhanDienBienSo`. Chạy `run.cmd`, mở http://127.0.0.1:8000. `/api/health` cần trả `status=ready`, phiên bản 1.3.0 và SHA-256 detector khớp `training.json`. API tự chọn CUDA nếu có; OCR chạy CPU. Lần suy luận đầu có thể chậm do warmup.

Chạy một worker. Bộ nhớ voting không chia sẻ giữa nhiều worker hoặc nhiều máy. Khi API khởi động lại, phiên hết hạn 10 phút hoặc trình duyệt bắt đầu phiên mới, trạng thái chống lặp đặt lại. Cơ sở dữ liệu và ảnh vẫn còn. API ảnh đơn không dùng voting.

## Hiệu chỉnh camera

Chọn vị trí sao cho ký tự đủ lớn, hạn chế nghiêng, lóa và xe di chuyển quá nhanh. Dùng vùng nhận diện theo % cho đúng làn; xem khung đã cắt trước khi đưa vào vận hành. Ảnh lưu là vùng đã cắt. Nếu vùng bao quá nhiều nền hoặc loại mất biển, quay về x=0, y=0, rộng=100, cao=100.

Mục tiêu nhận diện mặc định 5 lượt/s; hình xem trực tiếp yêu cầu 30 FPS. Hai con số khác nhau. Theo dõi tốc độ thực đạt và tỷ lệ cần kiểm tra; không tăng lên 10 nếu máy liên tục xử lý chậm. Camera trình duyệt lấy hình mới sau mỗi phản hồi. CLI/OpenCV phụ thuộc buffer và driver; không dùng thông số yêu cầu FPS làm bằng chứng FPS thực.

Ít nhất 3 quan sát rõ cùng chuỗi trong 7 quan sát gần nhất, chiếm ít nhất 60%, mới có trạng thái ổn định. Gán track dùng IoU và dự đoán vận tốc, không dùng danh tính hoặc biển số làm khóa ghép. Trường hợp ghép mơ hồ tạo track mới. Track biến mất quá 2,5 giây hết hạn; chống lưu lại cùng biển trong một phiên kéo dài 30 giây. Không dùng số track làm số xe thực.

Khi nhận diện thiếu sáng/mờ/nhỏ, không đoán ký tự để hoàn tất luồng: xem ảnh, chụp lại khi xe chậm hoặc đối chiếu bằng người. `needs_review` độc lập với điểm OCR. Voting không giải quyết mờ nặng, biển giả hay biển bị che.

## Truy cập từ máy khác

Mặc định chỉ localhost. Nếu triển khai nội bộ, đặt `PLATE_API_KEY` bằng bí mật đủ dài trong shell trước khi chạy; file `.env` không tự được nạp. Cấu hình giao diện chỉ giữ key trong phiên trình duyệt và gửi `X-API-Key`.

Đặt API sau reverse proxy HTTPS và giới hạn kích thước/tần suất request nếu mở truy cập mạng. Browser camera trên máy khác cần HTTPS. Chỉ cấp quyền cho người được phép đọc/xóa toàn bộ lịch sử: hiện API key là quyền chung, chưa có tài khoản hay vai trò riêng. Giữ một worker, tránh public port 8000 trực tiếp. Chưa đo tải nhiều camera hoặc vận hành 24/7.

## Sao lưu và khôi phục

```powershell
.\.venv\Scripts\python.exe scripts\maintenance.py backup --output .local/backups/history-20261006.zip
.\.venv\Scripts\python.exe scripts\maintenance.py verify .local/backups/history-20261006.zip
```

Chọn tên mới cho mỗi backup. Công cụ giữ khóa ghi SQLite trong khi chụp snapshot và sao chép các ảnh tham chiếu; yêu cầu ghi đồng thời có thể chờ. Backup chứa SQLite, ảnh và manifest SHA-256; không gồm model, mã nguồn hoặc API key. Model/code đã ở Git, OCR được tải và kiểm tra bằng `download_ocr.py`. Lưu thêm bản backup ngoài ổ máy để chịu được lỗi ổ đĩa.

Để khôi phục: dừng API; chạy verify; giải nén backup vào một thư mục **runtime mới trống** bằng công cụ giải nén thông thường; giữ runtime cũ nguyên vẹn; đặt `PLATE_DATA_DIR` tới thư mục mới; khởi động API và kiểm tra số bản ghi/ảnh. Không giải nén đè cơ sở dữ liệu đang mở. Đã thử khôi phục snapshot 60 bản ghi/86 ảnh và SQLite integrity_check trả ok.

## Chính sách lưu giữ

```powershell
.\.venv\Scripts\python.exe scripts\maintenance.py prune --days 30
# Sau khi backup và đọc kết quả dry-run:
.\.venv\Scripts\python.exe scripts\maintenance.py prune --days 30 --apply
```

Không có tự động xóa theo lịch. Dry-run không thay đổi dữ liệu. `--apply` xóa các bản ghi đủ tuổi và ảnh không còn tham chiếu; giữ những lượt đã liên kết với bằng chứng bãi xe cũ. Quyết định thời gian lưu theo nhu cầu vận hành. Giới hạn request 10 MB/16 triệu pixel vẫn áp dụng; health có `storage_free_mb` để theo dõi dung lượng.

## Kiểm chứng trước nghiệm thu

Tạo tập theo camera và ngày quay, tách khỏi dữ liệu phát triển. Gán nhãn tất cả lượt xe, cả lượt không đọc được; đánh giá ngày, đêm, mưa, lóa và mờ riêng. Đo tỷ lệ đọc đúng cả biển theo lượt, bỏ sót, sai ổn định, lặp sự kiện, độ trễ p95, mất khung, reconnect và ảnh còn truy cập sau nhiều giờ. Đặt ngưỡng nghiệm thu trước khi chạy test. Chưa có kết quả cho mưa thật, camera của người dùng hoặc chạy dài hạn.

Mã nguồn dùng AGPL-3.0. Theo tài liệu [Ultralytics YOLO11](https://docs.ultralytics.com/models/yolo11/), model/công cụ có AGPL-3.0 và lựa chọn Enterprise. Rà soát giấy phép dữ liệu/model theo cách triển khai cụ thể; nguồn video không có khai báo giấy phép chỉ được giữ cục bộ để đánh giá, không phát hành kèm sản phẩm.
