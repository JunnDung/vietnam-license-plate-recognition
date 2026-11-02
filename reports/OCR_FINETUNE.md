# Fine-tune OCR biển số Việt Nam — 02/11/2026

Đây là thí nghiệm mới sau bản 1.4. Detector YOLO11n không đổi; OCR CCT S v2 global được fine-tune bằng Keras/PyTorch trên RTX 3060 Laptop 6 GB. Kiến trúc và pretrained thuộc FastPlateOCR; dự án thực hiện chuẩn bị dữ liệu, thích nghi OCR, kiểm soát đánh giá và tích hợp ứng dụng.

## Dữ liệu đã khóa trước training

Nguồn [VNLP](https://github.com/fict-labs/VNLP/tree/d0b38df15c961393a7a1189912476c3d8d1edbfc), archive SHA-256 `f9da66c4cb443375ff40be140628ccfb3dc35f22755d82e341299e05b07a4a21`. [Manifest đầy đủ](ocr_finetune_manifest.json) có SHA-256 `4a81ed7de5aff2905eb897b1737369f8f13d48a89d66824ae9e4a877387a7c8c`.

| Phân vùng | Crop | ID biển | Crop hai dòng |
|---|---:|---:|---:|
| Train | 26.939 | 15.123 | 13.137 |
| Validation | 1.959 | 1.959 | 855 |
| Test cuối | 1.855 | 1.855 | 833 |

Nối các ảnh cùng ID biển, cùng pixel ảnh nguồn hoặc cùng pixel crop thành nhóm liên thông **trước khi loại bản sao**. Chia theo hash nhóm với seed `vnlp-finetune-20261102`; train giữ các lần chụp khác nhau, validation/test giữ một ảnh xác định theo hash cho mỗi ID. Không có giao ID/nhóm/pixel giữa ba phần. Loại các ID của benchmark 2.000 biển cũ, bộ legacy37 và toàn bộ nhóm liên quan. Không lọc theo dự đoán hoặc độ dễ của model. Chỉ CSV train/validation được cung cấp cho trainer; 28.898 crop của hai phần đã đối chiếu lại checksum sau train.

Nhãn đọc từ tên file, chưa được người kiểm tra độc lập toàn bộ. Chưa biết nguồn pretrained upstream có trùng VNLP hay không. Chưa đối chiếu đầy đủ mức trùng nguồn với bộ train detector cũ, nên kết quả pipeline cũng chưa chứng minh holdout độc lập với train của mọi thành phần. Chưa chứng minh độc lập theo camera hoặc phiên quay, và chưa thấy giấy phép tái phân phối ảnh rõ ràng; ảnh nguồn không được đưa vào Git. Đây là holdout mới **của lần fine-tune OCR trong dự án**, không phải chứng nhận độc lập với mọi dữ liệu pretrained/detector.

## Huấn luyện và export

- Nạp nghiêm ngặt toàn bộ 1.061.339 tham số pretrained, giữ head quốc gia 66 lớp nhưng loss weight 0; chỉ quảng bá kết quả head biển số.
- AdamW, LR 1e-4, weight decay 0,0005, batch 32, seed 20261102, cosine + 5% warmup, EMA, mixed FP16. Tối đa 30 epoch, dừng sớm patience 6.
- Augmentation trong [YAML](ocr_finetune_augmentation.yaml); bổ sung mờ chuyển động, gamma và nhiễu ở mức vừa. Seed Compose được lưu rõ vì serializer bỏ trường này.
- Hoàn thành **16 epoch / 8.063,83 giây**, checkpoint tốt nhất **epoch 10**, training-validation slot exact **1929/1959 = 98,4686%**. Đây là metric chọn checkpoint, không phải số liệu test cuối. [Log từng epoch](ocr_finetune_log.csv), [training report và hash](ocr_finetune_training.json).
- Một lần chạy đầu được dừng vì lỗi metric upstream trung bình batch không đều. Sửa metric trả kết quả từng mẫu, kiểm thử 2 mẫu đúng + 1 sai phải bằng 2/3, rồi chạy lại cùng cấu hình. Không phải tìm cấu hình bằng test. [Bằng chứng](ocr_finetune_metric_audit.json). Các chỉ số phụ trung bình batch/head quốc gia không được dùng làm thành tích.
- Export TorchScript gặp lỗi kernel shape MaxBlurPool; dùng môi trường TensorFlow CPU riêng và **cùng trọng số FP32**, không train lại. ONNX dynamic batch 1/2/8; output plate 10×37, region 66. [Export/parity](ocr_finetune_export.json).
- Trên 32 ảnh validation, ONNX trùng chuỗi **32/32** với TensorFlow FP32 và checkpoint PyTorch gốc ở FP32/mixed FP16. Sai khác xác suất cực đại lần lượt 1,52e-6, 2,38e-7 và 6,82e-4. [Torch parity](ocr_finetune_torch_parity.json). Đây là kiểm chứng export trên mẫu, không thay thế đánh giá toàn tập.

## Protocol lựa chọn và test

So sánh baseline 1.4 với hai cách phục vụ cùng checkpoint: `single` đọc trực tiếp crop RGB, `variants` giữ xử lý nhiều biến thể của 1.4. Chỉ chọn bằng 1.959 validation. Gate chốt trước: tăng ≥0,5 điểm phần trăm crop exact; CER và số biển hai dòng đúng không giảm; p95 crop ≤110% baseline; legacy37 crop/pipeline không giảm. Bổ sung yêu cầu tỷ lệ phát hiện và đọc đúng mục tiêu không giảm. Nếu nhiều cách đạt, xếp theo exact cao hơn, CER thấp hơn rồi độ trễ thấp hơn. Nếu không cách nào đạt, giữ model phục vụ cũ và công bố candidate như thí nghiệm.

Test cuối chỉ chạy sau khi khóa checkpoint/cách phục vụ/mã đánh giá trong Git; không chỉnh model hay ngưỡng theo kết quả đó. Bộ 1.621 test cũ, nếu chạy lại, là hồi quy đã công bố, không còn là holdout để lựa chọn.

### Lựa chọn trên validation

| Phép đo / 1.959 mục tiêu | Baseline 1.4 | Fine-tune single | Fine-tune variants |
|---|---:|---:|---:|
| Crop đúng toàn chuỗi | 1898/1959 | **1929/1959** | 1928/1959 |
| Exact match | 96,89% | **98,47%** | 98,42% |
| CER | 116/15661 = 0,741% | **57/15661 = 0,364%** | 67/15661 = 0,428% |
| OCR p50 / p95 ms | 61,21 / 112,61 | **26,48 / 30,37** | 60,38 / 113,24 |
| Phát hiện + đọc đúng mục tiêu | 1847/1959 | **1860/1959** | 1859/1959 |
| Pipeline p50 / p95 ms | 98,34 / 159,42 | **57,94 / 85,33** | 99,34 / 162,30 |
| Legacy37 crop / pipeline | 37/37 / 37/37 | 37/37 / 37/37 | 37/37 / 37/37 |

Cả hai cách vượt sáu tiêu chí. Chọn **single** vì exact cao hơn; đồng thời CER và độ trễ cũng thấp hơn. Tăng ròng 31 crop đúng; tỷ lệ phát hiện cùng detector là 1886/1959 ở cả ba cách. [Mọi dự đoán và tiêu chí](ocr_finetune_validation.json), [quyết định khóa](ocr_finetune_selection.json). Code/model/config/mode được commit và push tại **`bf26eb664396ed82d6ba23ddbd970324679e5ed6` trước khi chạy test cuối**.

Stress trên 200 validation: thiếu sáng baseline **192/200**, single **195/200**; mưa/sương mô phỏng **182/200 → 191/200**; **mờ chuyển động mạnh giảm từ 106/200 xuống 104/200**. Không che giấu mức giảm; model mới chưa giải quyết được chữ mất chi tiết. Stress không phải tiêu chí thay model đã chốt và không được dùng để thay cấu hình sau test.

### Test cuối — chạy một lần sau khóa

[Báo cáo gốc, từng dự đoán và thời gian](ocr_finetune_test.json). Hash evaluator/inference/manifest/ONNX trong kết quả khớp quyết định khóa. Không chỉnh model/ngưỡng sau khi xem kết quả này.

| Phép đo / 1.855 mục tiêu | Baseline 1.4 | Fine-tune single 1.5 |
|---|---:|---:|
| Đúng cả biển | 1792/1855 | **1810/1855** |
| Crop exact match | 96,60% | **97,57%** |
| Wilson 95% | 95,68–97,34% | **96,77–98,18%** |
| CER | 110/14845 = 0,741% | **64/14845 = 0,431%** |
| Một dòng | 1008/1022 = 98,63% | **1009/1022 = 98,73%** |
| Hai dòng | 784/833 = 94,12% | **801/833 = 96,16%** |
| OCR mean / p50 / p95 ms | 71,26 / 58,25 / 109,03 | **28,25 / 27,81 / 30,69** |
| Phát hiện mục tiêu IoU ≥0,5 | 1762/1855 = 94,99% | 1762/1855 = 94,99% |
| Phát hiện + đọc đúng mục tiêu | 1706/1855 = 91,97% | **1720/1855 = 92,72%** |
| Pipeline p50 / p95 ms | 104,17 / 164,54 | **66,89 / 94,85** |

Sửa đúng **23** lỗi và làm sai thêm **5** mẫu baseline đúng; tăng ròng **18/1855 = 0,97 điểm phần trăm**. Exact McNemar hai phía **p = 0,000912234**, với giả định độc lập giữa mục tiêu; không suy ra độc lập giữa camera. CER giảm 46 lỗi ký tự; phần tăng exact chủ yếu ở biển hai dòng. Detector vẫn bỏ sót 93 mục tiêu, nên OCR trên crop nhãn tốt hơn tỷ lệ đúng toàn pipeline. Không thay bằng số validation 98,47% hoặc detector mAP 99,11% để quảng bá accuracy đọc biển.

Thời gian là phạm vi engine trong môi trường được ghi ở JSON, chưa gồm IO/HTTP/lưu ảnh. Raw prediction arrays được giữ trong Git để kiểm tra, nhưng API `/api/model` chỉ trả summary. Trọng số đang phục vụ chính là `models/plate_ocr_vn.onnx`, SHA-256 `5ad8cf39ce818b34b28f51e95efbed62e255b8b6131c0ceb35449949405796d9`; config SHA-256 `0335c74a305173bb6f393efed0fde03cadeaa0b649ed8e19f431016d8232d0a6`. Baseline riêng không bị ghi đè.

### Ứng dụng và video hồi quy

Clone Git sạch tại commit khóa đọc đúng ảnh hồi quy `54N46324` trên CPU khi không có baseline download hoặc `models/training`. Phép kiểm tra dùng lại môi trường runtime đã ghim dependency, chưa lặp toàn bộ cài đặt/dựng dữ liệu trên máy mới.

[API thật](ocr_finetune_api_smoke.json): ready 1.5.0, đúng hash OCR, đọc đúng ảnh trên; tám khung phát lại cùng ảnh chuyển pending → stable, `save=false` giữ lịch sử 0 → 0. Ảnh hỏng trả 400, trang chủ 200, model endpoint bỏ prediction arrays. CLI video trống 7 giây chạy đủ mốc 0/3/6 và 35 khung ở 5 Hz, không sinh biển giả. Đây là smoke chức năng, không phải accuracy/load/camera acceptance.

[Video với OCR mới, từng khung](ocr_finetune_video_regression.json): giữ clip/ROI/nhãn/ngưỡng từ bộ hồi quy phát triển trước đây.

| Clip | Khung lấy mẫu | Mục tiêu đọc stable | Chuỗi stable ngoài nhãn chưa xác minh | Pipeline p95 ms |
|---|---:|---:|---:|---:|
| Giao thông ban ngày | 140 | 5/5 | 0 | 98,19 |
| Xe máy trong nhà | 18 | 1/1 | 0 | 88,26 |
| Giao thông đêm, toàn khung | 90 | 3/3 | 0 | 121,85 |
| Cùng clip đêm, ROI đã định | 90 | 3/3 | 3 | 161,80 |

Không cộng toàn khung và ROI thành các mục tiêu khác nhau. Ba chuỗi ROI ngoài nhãn (`65A20741`, `65H02902`, `66R00168`) chưa xác minh: có thể là biển không được gán nhãn hoặc đọc sai, không được tính mặc nhiên là đúng hay false positive. Không chọn lại ROI/ngưỡng sau kết quả; toàn khung vẫn là mặc định. Chưa có mưa thật hoặc camera USB/RTSP người dùng. Độ trễ video chỉ tính engine, không gồm seek/decode/HTTP/lưu ảnh; clip được dùng phát triển trước đây nên không là test độc lập.

### Kiểm chứng phần mềm và báo cáo

- Runtime: **33 test được phát hiện, 31 đạt và hai test backend được bỏ qua có chủ đích**. Hai test đó chạy riêng trong `.venv-train` và đều đạt: metric trọng số theo mẫu và seed augmentation. Hai bộ điều khiển JavaScript camera/video và kiểm tra cú pháp đều đạt.
- Tab model đã được kiểm tra bằng Edge: hiển thị 1.855 mẫu, OCR/video mới và ba chuỗi ROI chưa xác minh; không có lỗi JavaScript hoặc tràn ngang ở màn hình 390 px. [Ảnh giao diện](ocr_finetune_interface.png). Chưa thử camera vật lý hay tự động hóa upload video trình duyệt trong lượt 1.5.
- [DOCX đồ án 1.5](Bao_cao_do_an_nhan_dien_bien_so.docx): **30 trang**, cập nhật mục lục bằng Word, render LibreOffice và kiểm tra hình từng trang. Đã sửa trang gần trống, bảng bị tách và nhãn biểu đồ nhỏ/chồng nhau. Kết quả cũ được phân biệt với thí nghiệm mới.

Exact match = đúng toàn chuỗi / toàn bộ mục tiêu; CER = tổng Levenshtein / tổng ký tự nhãn, gồm cả dự đoán rỗng. Wilson 95% và exact McNemar hai phía được báo cáo cùng số cặp sửa đúng/làm sai thêm. Các phép thống kê giả định độc lập giữa mục tiêu, chưa mô hình hóa hết phụ thuộc cảnh chụp.

Pipeline chọn hộp IoU cao nhất với nhãn, không nhìn chuỗi để matching; yêu cầu IoU ≥0,5 và đúng toàn chuỗi. Không có hộp hoặc OCR sai đều tính thất bại. Ảnh nguồn chưa gán nhãn mọi biển nên chỉ gọi **annotated-target success**, không công bố full-scene precision/mAP từ phép đo này.

Đo warmed CPU ONNX hai luồng, detector CUDA/input640/conf0,35/max20 trên cùng máy; năm warmup mỗi layout/model, một detector warmup, luân phiên thứ tự model. OCR latency gồm tiền xử lý/giải mã chọn chuỗi, không gồm file IO/detector/HTTP. Pipeline latency có detector/OCR/quality, không có IO/HTTP/lưu lịch sử. Không chuyển crop/giây thành FPS camera. Stress trên 200 validation theo hash, giữ mọi mẫu sau biến đổi, chỉ là mô phỏng.

## Tái lập

Môi trường runtime, train và export tách riêng; xem `requirements-lock.txt`, `requirements-ocr-train-lock.txt`, `requirements-ocr-export-lock.txt`. Các lệnh sau chạy từ thư mục dự án. Cần archive VNLP ghim hash tại `data/raw/VNLP_detection.zip`; URL tải được ghi trong [benchmark cũ](OCR_BENCHMARK.md). Để dựng lại dữ liệu mới, cần chạy `scripts/prepare_data.py` trước để có ảnh legacy37 dùng xác định nhóm loại trừ.

```powershell
# Dựng ảnh train/val/test vào data/, ghi manifest tái lập ở output mới.
.\.venv\Scripts\python.exe scripts/prepare_data.py
.\.venv\Scripts\python.exe scripts/prepare_ocr_training.py --manifest .local/replayed_finetune_manifest.json
.\.venv\Scripts\python.exe -c "from pathlib import Path; assert Path('.local/replayed_finetune_manifest.json').read_bytes()==Path('reports/ocr_finetune_manifest.json').read_bytes()"

# Tạo môi trường train riêng, không cài vào Python hệ thống/runtime API:
py -3.12 -m venv .venv-train
.\.venv-train\Scripts\python.exe -m pip install -r requirements-ocr-train-lock.txt --extra-index-url https://download.pytorch.org/whl/cu128
.\.venv-train\Scripts\python.exe scripts/train_ocr.py --name reproduced_ocr
# Script xác minh hash crop/CSV và tải asset pretrained theo digest trước train.

# Khôi phục mã baseline chính xác để đánh giá từ clone sạch:
New-Item -ItemType Directory -Force .local/ocr-finetune | Out-Null
.\.venv\Scripts\python.exe -c "from pathlib import Path; import subprocess; Path('.local/ocr-finetune/baseline_recognition.py').write_bytes(subprocess.check_output(['git','show','8f03947f51e37bdd626960f9d109d9e0e29c4502:recognition.py']))"

# Dựng lại ảnh và dùng artifact đã đóng gói để đối chiếu kết quả, không cần train lại:
.\.venv\Scripts\python.exe scripts/download_ocr.py
.\.venv\Scripts\python.exe -c "from pathlib import Path; from scripts.train_ocr import fetch_assets; fetch_assets(Path('models/training'))"
.\.venv\Scripts\python.exe scripts/evaluate_ocr_finetune.py --weights models/plate_ocr_vn.onnx --split test --mode single --output .local/replayed_finetune_test.json
```

Export và đánh giá dùng `scripts/export_ocr.py`, `scripts/evaluate_ocr_finetune.py`; xem `--help`. Chỉ ghi output mới, giữ báo cáo gốc. Khi tái lập phép đo độ trễ, tắt các tác vụ nặng đồng thời; latency có thể thay đổi theo máy/tải. Kết quả detector 99,11% mAP@50 / 87,50% mAP@50–95 là bộ test detector cũ 665 ảnh, tách biệt số liệu OCR mới.

Seed và lock giúp tái lập quy trình; không bảo đảm train lại trên CUDA cho checkpoint giống từng byte. Muốn đối chiếu số liệu nhận dạng đã công bố, dùng đúng artifact ONNX/config có hash đi kèm. Để dựng đồ thị/báo cáo, cài `requirements-report.txt` trong môi trường authoring riêng, chạy `scripts/plot_ocr_finetune.py` rồi `scripts/build_report.py`; phần render/kiểm tra bố cục cần Word hoặc LibreOffice.
