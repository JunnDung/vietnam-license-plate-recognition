# Biển Số Việt

Hệ thống nhận diện biển số ô tô và xe máy Việt Nam từ ảnh, camera và video: mô hình **YOLO11n được fine-tune tại máy**, OCR **CCT S v2 có sẵn**, API FastAPI và giao diện tiếng Việt. Có tra cứu lịch sử, xem ảnh nguồn và xuất CSV. Dữ liệu được lưu bằng SQLite, ảnh lưu tại máy chạy server.

## Chạy trên Windows

Máy đang phát triển đã có môi trường `.venv` tại `D:\ComputerVision`. Chạy `run.cmd`, rồi mở **http://127.0.0.1:8000**. Nếu server đã chạy, chỉ cần mở địa chỉ này.

Trên máy mới, dùng Python 3.12 (hỗ trợ 3.11–3.13):

```powershell
git clone https://github.com/JunnDung/vietnam-license-plate-recognition.git
cd vietnam-license-plate-recognition
powershell -ExecutionPolicy Bypass -File .\setup.ps1
.\run.cmd
```

Nếu cần GPU NVIDIA cho huấn luyện, dùng `setup.ps1 -Cuda`. Có thể chỉ định Python bằng `-Python C:\path\python.exe`. Bộ cài chỉ tạo môi trường riêng trong dự án. OCR được tải một lần từ nguồn upstream; lần chạy sau xử lý ảnh bằng các file model trên máy.

Trên Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-lock.txt
python scripts/download_ocr.py
uvicorn app:app --host 127.0.0.1 --port 8000
```

## Sử dụng

- **Nhận diện:** chọn/kéo thả ảnh JPG, PNG hoặc WebP; điều chỉnh ngưỡng phát hiện; xem vùng biển số, ký tự và độ tin cậy.
- **Camera trình duyệt:** cho phép camera tại localhost/HTTPS. Yêu cầu hình xem trực tiếp 30 FPS; nhận diện mặc định 5 lượt/giây, chọn 1/2/5/10 và xem tốc độ thực đạt. Lấy khung rõ hơn trong 3 khung cách khoảng 33 ms, xử lý tuần tự rồi lấy khung mới, không dồn yêu cầu. Dừng khi đổi tab hoặc rời trang. Nếu bật lưu, mỗi khung có biển tạo bản ghi mới; bỏ chọn lưu khi quan sát để tránh ghi nhiều ảnh lặp.
- **Video:** chọn MP4/WebM/OGV mà trình duyệt giải mã được, tối đa 500 MB và 10 phút. Chọn 1/2/5/10 khung mỗi giây video, bấm **Phân tích video**, tạm dừng/tiếp tục hoặc quét lại. Kết quả có mốc giây, nút xem lại khung và CSV; chỉ hiển thị 100 kết quả gần nhất, CSV chứa tất cả kết quả. Mặc định không lưu lịch sử; tích lưu để tra cứu khung về sau. Video được giải mã tại trình duyệt, chỉ các JPEG gửi đến API ảnh hiện có; không tải toàn bộ video lên server. Các khung mẫu đều được xử lý theo thứ tự, nên video có thể quét chậm hơn thời gian thực. Nhiều kết quả cùng biển không tương đương nhiều xe. AVI hoặc video dài dùng CLI.
- **Tra cứu:** tìm một phần hoặc toàn bộ biển số, lọc thời điểm, xem ảnh nguồn, xuất CSV, xóa lượt nhận diện. Thời gian giao diện theo Việt Nam (UTC+7); API/CSV dùng UTC.
- **Kết quả mô hình:** hiển thị các phép đo từ `reports/`. mAP là kết quả phát hiện vùng biển số, không phải tỷ lệ đọc đúng ký tự.

Tra cứu chỉ tìm những lượt hệ thống đã ghi nhận. Hệ thống không kết nối cơ sở dữ liệu chủ xe hoặc đăng ký phương tiện.

Giao diện hiện tập trung vào nhận diện, lịch sử và kiểm chứng mô hình; tab bãi giữ xe cùng thao tác xác nhận vào/ra đã tạm bỏ theo phạm vi hiện tại. Dữ liệu và API bãi xe cũ được giữ để tương thích, chưa có thao tác ghi nhận lượt gửi trên giao diện. Các ảnh đã được tham chiếu trong lượt gửi cũ vẫn được bảo vệ khỏi xóa riêng trong lịch sử.

Camera USB, file video hoặc RTSP cũng có thể chạy bằng CLI:

```powershell
.\.venv\Scripts\python.exe scripts\camera.py --source 0
.\.venv\Scripts\python.exe scripts\camera.py --source D:\video.mp4 --fps 5 --save
.\.venv\Scripts\python.exe scripts\camera.py --source "rtsp://CAMERA_ADDRESS/stream" --fps 5
```

CLI mở nguồn camera ở phía máy chạy script rồi gửi ảnh đến API; server không truy cập URL camera do người dùng gửi lên. CLI mặc định không lưu và lấy mẫu mục tiêu 5 lượt/giây; `--fps 1` đến `--fps 10` điều chỉnh, `--interval 3` giữ cách lấy mẫu cũ. JSON mỗi dòng có `video_time` và `processing_ms`; Ctrl+C để dừng. File video quét hết các mốc lấy mẫu, không nhất thiết thời gian thực. USB/RTSP yêu cầu 30 FPS và buffer 1 khung nhưng driver có thể bỏ qua, chưa kiểm chứng phần cứng.

CLI chọn khung có điểm chi tiết cao hơn trong tối đa 3 khung liên tiếp, giảm burst khi FPS nguồn thấp để giữ đủ mốc video; `--burst 1` tắt và `--burst 5` tăng số khung so sánh. Đây là điểm trên toàn ảnh, không bảo đảm biển số rõ. Hướng dẫn ban đêm, trời mưa, màn trập và nghiệm thu: [CAMERA_GUIDE.md](reports/CAMERA_GUIDE.md).

API mặc định `PLATE_DEVICE=auto`: detector chạy CUDA khi có GPU phù hợp, nếu không dùng CPU; OCR vẫn dùng CPU. Đặt `PLATE_DEVICE=cpu` để ép CPU, rồi khởi động lại server. Không giảm input detector 640 hoặc đổi độ chính xác model để tăng FPS. Phép đo warmed inference trên 37 ảnh: CPU trung bình 141 ms, GPU 108 ms; chưa gồm trình duyệt, burst, HTTP và lưu ảnh. Kiểm chứng video/tốc độ: [VIDEO_VALIDATION.md](reports/VIDEO_VALIDATION.md).

## API xử lý ảnh

Tài liệu tương tác: **http://127.0.0.1:8000/docs**.

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/recognize `
  -F "file=@D:\image.jpg" -F "source=upload" -F "confidence=0.35" -F "save=true"
```

```python
import httpx

with open('image.jpg', 'rb') as file:
    response = httpx.post(
        'http://127.0.0.1:8000/api/recognize',
        files={'file': ('image.jpg', file, 'image/jpeg')},
        data={'confidence': '0.35', 'save': 'false'},
        timeout=120,
    )
response.raise_for_status()
print(response.json())
```

| Endpoint | Chức năng |
|---|---|
| `GET /api/health` | Trạng thái model và yêu cầu API key |
| `POST /api/recognize` | Ảnh multipart → danh sách vùng biển số, ký tự, độ tin cậy, thời gian xử lý |
| `GET /api/history?plate=51A&limit=30&offset=0` | Tra cứu phân trang |
| `GET /api/history.csv` | Xuất kết quả theo cùng bộ lọc |
| `GET /api/images/{id}` | Ảnh nguồn/crop của lượt đã lưu |
| `DELETE /api/history/{id}` | Xóa bản ghi và ảnh không còn được bản ghi khác dùng |
| `GET /api/model` | Các báo cáo kiểm chứng |
| `GET /api/parking?status=active&plate=51A` | Xe đang trong bãi, lượt gửi, số lượt vào/ra hôm nay |
| `POST /api/parking/events` | Ghi nhận xe vào/ra đã được người vận hành đối chiếu |

`since` và `until` nhận ISO 8601 kèm múi giờ, ví dụ `2026-10-06T20:00:00+07:00` (URL encode dấu `+`). Giới hạn ảnh: 10 MB, 16 triệu pixel, cạnh tối thiểu 32 px; tối đa 20 biển số mỗi lượt. Upload phải có `Content-Length`, như browser FormData và httpx/curl gửi file thông thường. `save=false` không ghi ảnh hoặc kết quả vào lịch sử. Nhận diện không có biển số trả HTTP 200 với danh sách rỗng, không tạo dữ liệu giả.

`valid_format` chỉ kiểm tra một số mẫu biển dân dụng phổ biến. `needs_review` bật khi OCR dưới 0.8 hoặc định dạng không phù hợp. Điểm tự tin cao vẫn có thể sai; luôn đối chiếu ảnh khi kết quả dẫn đến quyết định thực tế. Không tự đổi O/0 hoặc I/1 để ép thành biển số hợp lệ.

API bãi xe dưới đây được giữ cho tương thích với bản cũ; giao diện hiện tại không sử dụng. Ví dụ xác nhận lượt gửi từ một `detections[].id` đã lưu:

```json
{
  "record_id": "ID_32_KY_TU_CUA_LUOT_NHAN_DIEN",
  "plate": "51A-123.45",
  "direction": "in",
  "confirmed": true
}
```

Xe ra dùng `direction: "out"` và **một lượt nhận diện mới**. Endpoint yêu cầu `confirmed=true`, ảnh đã lưu và biển số hợp lệ; từ chối ảnh đã được dùng, lượt vào trùng hoặc xe ra không có lượt vào đang mở. Quyết định cổng được ghi trong transaction SQLite; unique index ngăn hai cổng đồng thời tạo hai lượt gửi cho cùng biển số. `GET /api/parking` hỗ trợ `status=active|closed|all`, `plate`, `limit` và `offset`.

## Huấn luyện lại

Dữ liệu được tìm bằng **Hugging Face MCP**: [Vietnam License Plate Segment Datasets](https://huggingface.co/datasets/hoanglvuit/Vietnam_License_Plate_Segment_Datasets). Thư viện được kiểm tra qua **Context7 MCP**; tài khoản GitHub được xác nhận qua connector GitHub.

```powershell
.\.venv\Scripts\python.exe scripts\prepare_data.py
.\.venv\Scripts\python.exe scripts\train.py --epochs 40 --batch 16 --workers 2 --device 0
.\.venv\Scripts\python.exe scripts\evaluate_robustness.py --samples 200 --device 0
.\.venv\Scripts\python.exe scripts\evaluate_ocr.py --device cpu
```

`prepare_data.py` tải archive, kiểm tra ảnh/nhãn polygon, chuyển nhãn sang bounding box, loại ảnh trùng pixel và chia theo nhóm tiền tố + khối số thứ tự 25 ảnh. Split seed 42: **3.189 train / 674 val / 665 test**; loại 44 ảnh trùng và 6 nhãn lỗi. Script giữ nguyên split nếu dữ liệu đã chuẩn bị; không âm thầm ghi đè. `reports/dataset.json` lưu hash archive, danh sách ảnh/split và các mẫu loại bỏ.

Model khởi tạo từ `yolo11n.pt`; augment độ sáng, quay nhẹ, scale và mosaic. Không lật ngang/dọc ký tự. Checkpoint tốt nhất được chọn bằng validation; **test được đánh giá sau khi kết thúc huấn luyện**, không dùng để chọn checkpoint. Muốn tiếp tục một lượt gián đoạn, chạy `train.py --resume` khi `runs/plate_detector/weights/last.pt` còn tồn tại. Để train một thí nghiệm mới, di chuyển thư mục run cũ trước khi chạy.

OCR là mô hình pretrained [fast-plate-ocr](https://github.com/ankandrew/fast-plate-ocr), không được fine-tune ở dự án này vì dataset không có phiên âm đầy đủ. Pipeline thử crop gốc, ghép hai dòng cho biển vuông và CLAHE. Cần nhãn ký tự thực tế để fine-tune OCR riêng cho camera của bạn.

### Fine-tune chống mờ và chọn model

Bản cập nhật đã hoàn thành **18 epoch bổ sung sau 40 epoch nền**. Recall detector mờ ngang mô phỏng tăng **80.43% → 97.39%**, mờ chéo **44.78% → 95.65%**, mưa kèm mờ **76.52% → 97.39%**. Ở ngưỡng 0.35, recall ảnh gốc/tối/mưa đơn giảm nhẹ; bảng đầy đủ trong [VALIDATION.md](reports/VALIDATION.md). OCR mờ nặng vẫn chỉ đúng **3/37**, nên cần khung rõ và người xác nhận.

`train_robust.py` chỉ tạo candidate; `validate_robust.py` chọn bằng validation rồi mới đo test và thay model. Để tái lập từ v1, trích file nhị phân và báo cáo bằng Python (không dùng chuyển hướng văn bản PowerShell cho `.pt`):

```powershell
.\.venv\Scripts\python.exe scripts\prepare_data.py
.\.venv\Scripts\python.exe -c "from pathlib import Path; import subprocess; p=Path('.local/v1'); p.mkdir(parents=True,exist_ok=True); names=['models/plate_detector.pt','reports/training.json','reports/robustness.json','reports/ocr_evaluation.json']; [(p/Path(n).name).write_bytes(subprocess.check_output(['git','show','7f584eb:'+n])) for n in names]"
.\.venv\Scripts\python.exe scripts\evaluate_ocr.py --weights .local/v1/plate_detector.pt --weather --output .local/v1/ocr_weather.json
.\.venv\Scripts\python.exe scripts\train_robust.py --weights .local/v1/plate_detector.pt --name plate_robust_replay --device 0
.\.venv\Scripts\python.exe scripts\validate_robust.py --baseline .local/v1/plate_detector.pt --baseline-report-dir .local/v1 --baseline-ocr-weather .local/v1/ocr_weather.json --run plate_robust_replay --device 0
```

Run đã tồn tại sẽ bị từ chối để giữ checkpoint; dùng tên mới khi lặp thí nghiệm. Sau khi thay model cần khởi động lại server. `evaluate_robustness.py --extended --output reports/robustness_extra.json` đo thêm thiếu sáng xám có nhiễu, mờ chéo và mưa kèm mờ. Không dùng kết quả test để chọn checkpoint/ngưỡng; test hiện tại đã được dùng chẩn đoán v1 nên là benchmark hồi quy, vẫn cần tập độc lập theo camera.

## Đánh giá và giới hạn

- `reports/training.json`: cấu hình, GPU, hash model và mAP/precision/recall trên tập test.
- `reports/training_curve.csv`: số liệu mỗi epoch; `results.png`: đồ thị train/validation.
- `reports/robustness.json`: kiểm tra cùng 200 ảnh test với thiếu sáng, mưa/sương và mờ chuyển động **mô phỏng**, cùng ngưỡng confidence 0.35, matching đúng lớp tại IoU ≥ 0.5.
- `reports/ocr_ground_truth.json`: mẫu test được chọn trước dự đoán, phiên âm trực tiếp bằng mắt, ghi các mẫu không thể đọc và ghi chú sửa nhãn sau kiểm tra phóng to. Cần người khác kiểm tra độc lập nhãn này.
- `reports/ocr_evaluation.json`: tỷ lệ đọc đúng cả biển, CER trên crop và tỷ lệ đúng cả quy trình trên mẫu nhỏ đã phiên âm.
- `reports/ocr_weather.json`: cùng mẫu OCR dưới các biến đổi thiếu sáng/mưa/mờ, không loại thêm ảnh sau biến đổi.
- `reports/hardening.json`: so sánh baseline/candidate, tiêu chí chọn bằng validation và kết quả test sau khi đã chốt model.
- `reports/robustness_extended.json`: bảy điều kiện detector mô phỏng với before/after trên cùng ảnh.
- `reports/VALIDATION.md`: kết quả cuối cùng và phạm vi các kiểm tra chạy thực tế.
- [Báo cáo kỹ thuật DOCX](reports/Bao_cao_nhan_dien_bien_so_va_bai_giu_xe.docx): 25 trang của phiên bản nền tại commit `7f584eb`; kết quả cập nhật sau đó xem `VALIDATION.md` và các JSON hiện tại.

Dataset không có camera/vehicle IDs, nhãn thời tiết hoặc nhãn ngày/đêm. Chia nhóm và loại trùng pixel giảm rò rỉ, nhưng **không chứng minh không còn cùng biển số ở các split**. Kiểm tra mô phỏng và mẫu OCR nhỏ không chứng minh chất lượng cho mọi camera ban đêm, trời mưa, biển bị lóa, che khuất hoặc rất nhỏ. Trước khi dùng camera thực tế, cần một tập test theo camera/phiên quay với ngày/đêm/mưa được gán nhãn riêng. Crop OCR dùng phép ghép hai dòng đơn giản; biển nghiêng mạnh có thể cần model keypoint để nắn phối cảnh.

## Kiểm tra phần mềm

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check web/app.js
node tests/check_camera_js.cjs
# Khi API đang chạy:
.\.venv\Scripts\python.exe tests\check_camera.py
```

Contract checks dùng inference giả để kiểm tra upload, xác thực, lưu/tìm/xóa, CSV, xác nhận xe vào/ra, bảo vệ bằng chứng và hai cổng cùng ghi nhận một biển số. Các báo cáo model và thử API với ảnh thực dùng model thật. `tests/check_camera.py` gửi video trống 7 giây đến API đang chạy và kiểm tra khung hình giây 0/3/6. Workflow GitHub chạy contract checks trên CPU; không huấn luyện lại hoặc tự tạo ra benchmark trong CI.

## Lưu trữ và triển khai

Mặc định server chỉ lắng nghe `127.0.0.1`. Biến môi trường: `PLATE_DEVICE=cpu` hoặc `0`, `PLATE_DATA_DIR` để đổi thư mục lưu, `PLATE_API_KEY` để bảo vệ API. File `.env.example` là ví dụ; ứng dụng không tự đọc `.env`.

Nếu mở trong LAN/Internet, đặt API key, reverse proxy HTTPS và giới hạn request; HTTPS cần cho camera trong browser ở máy khác. Giao diện cho nhập key và chỉ giữ trong sessionStorage, gửi bằng `X-API-Key`; không đưa key vào URL ảnh. Chưa có tài khoản nhiều người hoặc phân quyền từng bản ghi. Khóa inference toàn cục phù hợp một máy thực hành; chưa phải dịch vụ nhiều camera có hàng đợi và tracking.

Thư mục `runtime/` chứa ảnh/lịch sử; sao lưu cả SQLite lẫn thư mục ảnh khi server dừng. Có thể xóa từng lượt từ giao diện. Dữ liệu camera, dữ liệu train, môi trường, log, token và OCR download không đưa lên Git. Repo lưu code, model detector đã train và các báo cáo. Không có API key được hardcode.

## Nguồn và giấy phép

Code dự án theo AGPL-3.0, cùng chế độ mã nguồn mở của [Ultralytics](https://github.com/ultralytics/ultralytics). OCR lấy từ dự án MIT của [ankandrew/fast-plate-ocr](https://github.com/ankandrew/fast-plate-ocr). Dataset Hugging Face hiện không có README hoặc thông tin giấy phép rõ ràng; dữ liệu nguồn không được phân phối trong repo, cần xác nhận quyền dùng trước khi dùng thương mại. Repo này không thay đổi quyền hoặc giấy phép của dữ liệu/model bên thứ ba.
