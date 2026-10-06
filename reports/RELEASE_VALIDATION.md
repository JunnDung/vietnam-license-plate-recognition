# Kiểm chứng phiên bản 1.3.0 ngày 6 tháng 10 năm 2026

## Thay đổi và phạm vi

Không đổi trọng số detector hoặc OCR trong lượt này. Detector vẫn là YOLO11n fine-tune 40 epoch nền + 18 epoch chống mờ, SHA-256 `37a282619e923cc5715f81fe1f236e5c7fb281322d546f2aa3ae9a2de8ce49f6`. OCR CCT S v2 vẫn pretrained. Cải tiến ở luồng xử lý thời gian, lưu dữ liệu, giao diện và vận hành.

- Gán track theo hộp chuẩn hóa, dự đoán vận tốc và IoU; ghép mơ hồ tạo track mới.
- Ít nhất 3 quan sát rõ cùng chuỗi và ≥60% của tối đa 7 quan sát mới ổn định. Không dùng khung `needs_review` để bỏ phiếu.
- Một lần lưu cho cùng biển trong một track; chống lặp cùng biển giữa các track trong 30 giây của cùng phiên. Bộ nhớ có giới hạn và hết hạn, cần một worker.
- Replay cùng UUID/mốc/nội dung trả cùng request, không ghi trùng. Mốc đi lùi hoặc đổi nội dung cùng mốc bị chặn.
- ROI theo %, ảnh lưu là vùng cắt; giới hạn request và JPEG giữ nguyên. Lý do cần kiểm tra được lưu cho bản ghi mới.
- Backup SQLite + ảnh + hash; verify và phục hồi thử. Prune mặc định dry-run, giữ ảnh đã tham chiếu trong dữ liệu bãi xe cũ.

## Video thật công khai

Nguồn/revision/hash/nhãn trong `video_ground_truth.json`; toàn bộ dự đoán trong `real_video.json`. Không phát hành file video nguồn. Nhãn mục tiêu được phiên âm bằng mắt trước inference, chưa kiểm tra độc lập. Video ban ngày cũng được dùng để sửa lỗi association, vì vậy là **bộ hồi quy phát triển**, không phải holdout nghiệm thu. Không biết mức trùng nguồn với bộ train.

5 khung/giây, cạnh dài tối đa 1280, JPEG chất lượng 90, detector input 640 FP32 confidence 0.35, cùng OCR. Full frame và ROI định trước được ghi riêng.

| Clip | Khung | Biển chọn đọc được ở ít nhất một khung | Biển chọn đọc ổn định |
|---|---:|---:|---:|
| Giao thông ban ngày có xe di chuyển 27,86 s | 140 | 5/5 | 5/5 |
| Camera cầm tay trước xe máy đỗ trong nhà 3,47 s | 18 | 1/1 | 1/1 |
| Giao thông đêm xám 18,00 s toàn khung | 90 | 3/3 | 2/3 |
| Cùng clip đêm với ROI x0 y15 rộng50 cao80 % | 90 | 3/3 | 2/3 |

Biển đêm `65A18114` được đọc đúng ở một số khung nhưng OCR bất đồng, chưa đủ khung rõ thống nhất để đưa vào sự kiện ổn định. ROI không cải thiện số mục tiêu ổn định trong thử nghiệm này và tạo thêm một chuỗi ổn định ngoài danh sách 3 mục tiêu, chưa được xác minh. Không dùng bảng để tính precision toàn cảnh hoặc tuyên bố 100% mọi xe.

Pipeline detector + OCR trung bình lần lượt khoảng 72,39/119,69/124,71/168,11 ms; p95 137,87/131,80/268,31/286,56 ms. Các số không bao gồm toàn bộ seek/giải mã/JPEG/HTTP/storage. Thời gian chạy đầy đủ CLI từng clip được ghi riêng trong JSON. Có một blank warmup detector; lần OCR đầu nằm trong phép đo.

Browser/API thật với MP4 xe máy: xử lý 18 khung ở mức lấy mẫu 5 Hz, có 1 lượt biển ổn định `59V184625`, xem lại khung 3,20 s. Tốc độ xử lý quan sát 3,3 lượt/s; không đồng nhất với FPS nguồn hoặc FPS xem trực tiếp. Khung sau vẫn có thể chuyển về cần kiểm tra. Không bật lưu, lịch sử người dùng còn nguyên 60 bản ghi. Bộ điều khiển CSV/grouping được kiểm tra bằng Node; tải CSV phụ thuộc trình duyệt.

## Kiểm tra phần mềm và dữ liệu

9 unittest đạt: boundaries/auth/storage, quality/disagreement, corruption, chọn model, temporal isolation/fast motion/gaps/replay/dedup và backup/retention/corruption. Node checks camera/video đạt, gồm ROI kích thước và gộp sự kiện ổn định. API thật nhận 8 khung cùng biển không lưu và trả pending rồi stable.

Backup cục bộ 60 records/86 ảnh: hash verify đạt, giải nén vào thư mục thử riêng, SQLite integrity_check=ok và số records=60. Dry-run retention 30 ngày trả 0 records đủ điều kiện; không chạy xóa lịch sử người dùng. Migration thêm review_details, không thay ký tự hoặc xóa records cũ.

## Giới hạn còn lại

OCR mờ mạnh của phép đo ảnh trước vẫn chỉ 3/37 đúng cả biển. Chưa có video mưa thật, live USB/RTSP của người dùng, thử reconnect/mất điện/chạy 24 giờ hoặc benchmark nhiều camera. Voting có thể bỏ lỡ xe xuất hiện quá nhanh và có thể thống nhất một chuỗi OCR sai. Cần tập nghiệm thu theo camera/phiên quay với nhãn tất cả lượt xe trước khi cam kết chất lượng tại hiện trường.
