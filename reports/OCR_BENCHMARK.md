# Kiểm chứng OCR 1.4.0 — 02/11/2026

Đây là báo cáo lịch sử của **1.4.0**. Phiên bản **1.5.0** fine-tune OCR, dùng split mới loại toàn bộ 2.000 ID cũ và thay model sau khi vượt gate validation; xem [OCR_FINETUNE.md](OCR_FINETUNE.md). Các điểm 1.621 test dưới đây không phải chỉ số của model 1.5 và không dùng để chọn model mới. DOCX cũng đã được cập nhật riêng cho lượt 1.5; ghi chú chưa cập nhật DOCX ở cuối trang này mô tả phạm vi lúc phát hành 1.4.

## Phạm vi và mô hình

Đo khả năng đọc **đúng toàn bộ chuỗi trên crop biển số có nhãn**. Đây không phải accuracy toàn camera, mAP detector hay tỷ lệ xe được nhận diện ổn định trong video. Chuẩn hóa cả nhãn và dự đoán về chữ Latin viết hoa/chữ số; không tự thay O/0, I/1 hoặc dùng nhãn để sửa dự đoán.

Detector YOLO11n và OCR CCT S v2 giữ nguyên trọng số. Detector đã được fine-tune ở các lượt trước; **không train/fine-tune OCR trong lượt này**. OCR ONNX SHA-256 `384bbbd2cea3ef54761d3df70822ef3a349ee1a112aeafddbe0e3ba06bc6e47b`; cấu hình SHA-256 `0335c74a305173bb6f393efed0fde03cadeaa0b649ed8e19f431016d8232d0a6`. Nguồn tải/hash trong [ocr_provenance.json](../models/ocr_provenance.json).

Bản mới sửa BGR → RGB đúng [hợp đồng FastPlateOCR](https://github.com/ankandrew/fast-plate-ocr/blob/v1.1.0/fast_plate_ocr/inference/plate_recognizer.py), và lấy confidence đúng vị trí ký tự sau khi bỏ padding/dấu phân cách. Với biển hai dòng, thêm một phương án ghép dòng sau nắn phối cảnh: chỉ dùng khi tìm được viền sáng lồi bốn góc chiếm ít nhất 40% crop. Giữ các phương án gốc; chọn theo định dạng dân dụng rồi confidence như trước. Không tìm được viền phù hợp thì dùng các phương án cũ. Viền bẩn, màu tối, bị che hoặc lóa vẫn có thể thất bại; confidence chưa được hiệu chuẩn thành xác suất đọc đúng.

## Dữ liệu và quy trình cố định

- Nguồn: [VNLP của nhóm tác giả](https://github.com/fict-labs/VNLP/tree/d0b38df15c961393a7a1189912476c3d8d1edbfc), revision `d0b38df15c961393a7a1189912476c3d8d1edbfc`.
- Archive: 37.297 ảnh JPEG, SHA-256 `f9da66c4cb443375ff40be140628ccfb3dc35f22755d82e341299e05b07a4a21`. Chuỗi biển và hộp được đọc từ tên file theo chú thích của tác giả. Readme archive ghi nhầm width-height; bốn tọa độ được xử lý là hai góc x0/y0/x1/y1 sau kiểm tra crop trước inference.
- Kiểm tra tọa độ, giải mã, hash pixel crop; loại trùng pixel và nhóm cùng pixel nhưng nhãn mâu thuẫn. Lượt này không có ảnh lỗi/trùng/mâu thuẫn theo các kiểm tra đó. Điều này không chứng minh nhãn chuỗi hoàn toàn chính xác.
- Loại khỏi danh sách lựa chọn các ID biển đã có trong bộ hồi quy 37 ảnh. Còn 20.941 ID nguồn đủ điều kiện. Mỗi ID chọn một ảnh bằng thứ tự SHA-256 của `seed:source_member`; chọn 2.000 ID đầu theo SHA-256 của `seed:plate`.
- Seed và giới hạn được chốt trước dự đoán: `vnlp-20261102`, 2.000 ID. Phân chia theo hash ID modulo 5: 0 là dev, còn lại là test. **379 dev / 1.621 test**, không trùng ID biển. Dev có 209 biển một dòng/170 hai dòng; test có 879/742.
- [Manifest đầy đủ](ocr_benchmark_manifest.json), SHA-256 `6dabb55378b0d00e766ea0499510dce273a384ba644ed49a9904c7ae4712c13a`. `.gitattributes` giữ LF để hash không đổi giữa Windows/Linux.

Đây là tập kiểm tra được giữ lại trong **lượt phát triển này**, không chứng minh chưa từng xuất hiện trong dữ liệu pretrain upstream của OCR. Không có camera/session IDs để chứng minh khả năng tổng quát sang camera mới. Nhãn filename chưa được kiểm tra độc lập bằng người; một số mẫu dev có nhãn mơ hồ hoặc khác ký tự nhìn thấy. Không sửa nhãn/loại mẫu theo dự đoán. Kết quả đo độ khớp với nhãn phát hành, bao gồm mọi mẫu đã chọn và cả dự đoán rỗng.

Tác giả cung cấp tải miễn phí và yêu cầu trích dẫn, nhưng không thấy giấy phép phân phối lại rõ ràng. Repo giữ manifest, hash, báo cáo và mã; ảnh/archive chỉ lưu cục bộ. Xem bài báo và hướng dẫn trích dẫn ở trang VNLP trước khi tái sử dụng dữ liệu.

## Chọn candidate bằng dev

Baseline là `recognition.py` tại commit `920784a32eb23362200e644fc56c818579c05771`, cùng checkpoint OCR và cùng session CPU.

| Phương án | Đúng cả biển / 379 | Exact match | CER |
|---|---:|---:|---:|
| Baseline 1.3 | 364 | 96,04% | 1,055% |
| Sửa RGB/confidence | 363 | 95,78% | 0,989% |
| Thêm phương án nắn phối cảnh | 365 | 96,31% | 0,890% |

Gate chốt trước phép đo: số đúng trên dev phải tăng, CER không tăng và số đúng ảnh rõ trong hồi quy 37 mẫu không giảm. Candidate cuối đạt cả ba: sửa được 1 mẫu dev, không làm sai thêm mẫu vốn đúng; giữ 37/37 crop và pipeline trên bộ hồi quy rõ. Mức tăng dev nhỏ, chưa đủ để khẳng định cải thiện có ý nghĩa thống kê.

Hai thử nghiệm dev được giữ lại: [RGB](ocr_dev_rgb_20261102.json), [nắn phối cảnh](ocr_dev_rectified_20261102.json). Hồi quy/các điều kiện mô phỏng của hai bản: [ocr_legacy_paired_20261102.json](ocr_legacy_paired_20261102.json). Không dùng ảnh hoặc kết quả test để chọn phương án.

## Kết quả test cuối

Khóa mã tại commit `b3f046fe700d95e65838877545e5fdaee15fb466` trước khi chạy test. SHA-256 của `recognition.py`: `0a455c02789b627be008cd3cffc3b570fc7218dab325ee4140f181f8ee74795b`. Chạy test một lần trên toàn bộ 1.621 mẫu sau khi chốt; không sửa OCR theo kết quả này. [Báo cáo gốc với từng dự đoán, thời gian và hash](ocr_benchmark.json).

| Phép đo trên cùng test | Baseline 1.3 | Candidate 1.4 |
|---|---:|---:|
| Đúng cả biển | 1.562/1.621 | **1.565/1.621** |
| Exact match | 96,36% | **96,55%** |
| Wilson 95% | 95,33–97,17% | 95,54–97,33% |
| CER | 92/12.990 = 0,708% | **89/12.990 = 0,685%** |
| Một dòng | 862/879 = 98,07% | 864/879 = 98,29% |
| Hai dòng | 700/742 = 94,34% | 701/742 = 94,47% |
| Mean crop OCR | 66,09 ms | 72,80 ms |
| p50 / p95 | 60,42 / 83,07 ms | 60,08 / 110,16 ms |
| Crop/giây tuần tự | 15,13 | 13,74 |

Candidate sửa 6 mẫu vốn sai và làm sai thêm 3 mẫu vốn đúng, ròng tăng 3/1.621 (**0,185 điểm phần trăm**). Đây là mức tăng nhỏ; exact McNemar hai phía trên 9 cặp bất đồng cho p = 0,508, không đủ bằng chứng cải thiện có ý nghĩa thống kê ở mức 0,05. Không mô tả kết quả này là bước nhảy lớn về accuracy. Đổi lại, mean latency tăng khoảng 10%; p95 tăng khoảng 27 ms do thêm biến thể OCR cho một số crop. Giữ bản mới vì sửa đúng hợp đồng thư viện và đạt gate dev đã chốt, với chi phí/giới hạn được công bố.

Hồi quy rõ/tối/mưa mô phỏng vẫn 37/37 trên crop và pipeline. **Mờ chuyển động nặng vẫn chỉ 3/37 crop**, pipeline 4/37 so với 3/37 baseline. Không suy diễn thành đã xử lý tốt mọi mờ hoặc mưa thật.

## Cách tính và thời gian

Exact match = số chuỗi đúng hoàn toàn / tổng crop; CER = tổng khoảng cách Levenshtein / tổng ký tự nhãn, có tính insert/delete/substitute và dự đoán rỗng. Báo cáo kèm khoảng Wilson 95% cho exact match; khoảng này dựa trên giả định mẫu Bernoulli độc lập, không mô hình hóa mọi phụ thuộc giữa ảnh cùng camera. Có số liệu riêng một dòng/hai dòng và các trường hợp được sửa/làm sai thêm.

Đo crop OCR warmed bằng `perf_counter`, ONNX Runtime 1.30.0 CPU, 2 intra-op threads, Windows, AMD Ryzen 7 6800H. Input model RGB 128×64, batch các biến thể cho từng crop; bản cũ 2–3 biến thể, bản mới tối đa 4. Warmup 5 lần cho mỗi layout/mỗi bản; đảo thứ tự chạy baseline/candidate giữa các ảnh. Thời gian gồm tiền xử lý/OCR/chọn kết quả, không gồm file IO, detector, HTTP, giải mã video hoặc lưu ảnh. Crop/giây tuần tự suy từ mean latency, **không phải FPS camera**. RTX 3060 Laptop có sẵn nhưng OCR của ứng dụng vẫn chạy CPU.

## Tái lập từ clone sạch

Tạo môi trường theo README, tải OCR bằng script có kiểm tra checksum. Chạy từ thư mục dự án; cần khoảng 5 GB cho archive và ảnh đánh giá, ngoài môi trường/model.

```powershell
New-Item -ItemType Directory -Force data/raw,.local/baseline | Out-Null
Invoke-WebRequest -Uri 'https://drive.usercontent.google.com/download?id=1sNmk3U15qkw2xIJ58BmvDrbqLohBmZZY&export=download&confirm=t' -OutFile data/raw/VNLP_detection.zip
.\.venv\Scripts\python.exe scripts/prepare_ocr_benchmark.py --manifest .local/replayed_manifest.json
.\.venv\Scripts\python.exe -c "from pathlib import Path; assert Path('.local/replayed_manifest.json').read_bytes()==Path('reports/ocr_benchmark_manifest.json').read_bytes()"
.\.venv\Scripts\python.exe -c "from pathlib import Path; import subprocess; Path('.local/baseline/recognition.py').write_bytes(subprocess.check_output(['git','show','920784a:recognition.py']))"
.\.venv\Scripts\python.exe scripts/benchmark_ocr.py --split dev --baseline-module .local/baseline/recognition.py --output .local/replayed_dev.json
.\.venv\Scripts\python.exe scripts/benchmark_ocr.py --split test --baseline-module .local/baseline/recognition.py --output .local/replayed_test.json
```

Lệnh chuẩn bị kiểm tra SHA-256 archive trước khi tạo ảnh. Không ghi đè manifest/báo cáo đã có; dùng output mới khi tái lập. Accuracy phải khớp trên cùng môi trường/checkpoint; latency có thể khác theo tải máy. Khi phát triển phương án tiếp theo, test này đã được công bố: cần một tập đánh giá mới theo camera/phiên quay, không tiếp tục tối ưu trên nó rồi gọi là holdout độc lập.

## Kiểm tra ứng dụng

16 unittest đạt, gồm RGB từng biến thể, vị trí confidence, giới hạn nắn viền, split/dedup/metric, chặn manifest không hợp lệ, API summary không trả hàng nghìn dự đoán; các contract ảnh/lịch sử/temporal/backup trước đây vẫn đạt. Node syntax và kiểm tra camera/video đạt.

Đã dựng lại manifest từ toàn bộ 37.297 ảnh nguồn bằng lệnh tái lập ở trên: **trùng từng byte** với manifest được commit, đúng SHA-256 đã công bố. [GitHub Actions 41354217671](https://github.com/JunnDung/vietnam-license-plate-recognition/actions/runs/41354217671) thành công trên Linux ở commit source/evidence `81d1e5a9f113fb775e2c0124571ad74528d8033f`. Review mã trước khi chốt test và review số liệu/tài liệu trước merge không phát hiện lỗi cần sửa.

API thật 1.4.0 khởi động, detector CUDA (`device=0`) và đúng hash checkpoint; đọc ảnh hồi quy `54N46324`, `save=false` giữ lịch sử ở 0 bản ghi trên clone mới. `/api/model` trả số liệu 1.621 crop, bỏ prediction arrays; trang chủ trả 200 và asset 1.4.0. CLI video trống 7 giây chạy đủ 3 mốc 0/3/6 theo cách cũ và 35 khung theo 5 Hz mặc định, không sinh biển giả. Đây là smoke test chức năng lịch sử, không phải đo accuracy video hay tải nhiều camera. Dữ liệu vận hành không nằm trong Git nên clone không khôi phục lịch sử/ảnh của máy trước đó.

Chưa thử camera USB/RTSP thật, mưa thật, đo tải dài hạn hoặc dựng lại DOCX. DOCX 1.3.0 và kết quả video trước đây là tài liệu lịch sử; lượt này cập nhật báo cáo OCR/README và câu mô tả CV theo thiết kế đã duyệt.
