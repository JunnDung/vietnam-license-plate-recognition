"""Rebuild the Vietnamese capstone report from the measured project evidence.

Optional authoring dependencies: python-docx and Pillow. Run from the project root.
"""
import json
from pathlib import Path

from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT/'reports'
ASSETS = ROOT/'.local/current-report-assets'
ASSETS.mkdir(parents=True,exist_ok=True)
Image.open(REPORTS/'stream-interface.png').crop((410,810,1040,1580)).save(ASSETS/'stream-result.png')
OUT = REPORTS/'Bao_cao_do_an_nhan_dien_bien_so.docx'
read = lambda name: json.loads((REPORTS/(name+'.json')).read_text(encoding='utf-8'))
training, hardening, stress, weather = [read(name) for name in ('training','hardening','robustness_extended','ocr_weather')]
video, operations, ground_truth = [read(name) for name in ('real_video','operation_validation','video_ground_truth')]
document = Document()
section = document.sections[0]
section.page_width,section.page_height = Cm(21),Cm(29.7)
section.top_margin,section.bottom_margin = Cm(2),Cm(2)
section.left_margin,section.right_margin = Cm(2.5),Cm(2)
section.header_distance,section.footer_distance = Cm(.8),Cm(.8)
section.different_first_page_header_footer = True
for name in ('Normal','Title','Title Char','Subtitle','Subtitle Char','Heading 1','Heading 1 Char','Heading 2','Heading 2 Char','Heading 3','Caption','TOC 1'):
    try: style=document.styles[name]
    except KeyError: continue
    style.font.name='Times New Roman';style.font.color.rgb=RGBColor(0,0,0)
    style._element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'Times New Roman')
    for fonts in style._element.iter(qn('w:rFonts')):
        for attribute in ('asciiTheme','hAnsiTheme','eastAsiaTheme','cstheme'):
            fonts.attrib.pop(qn('w:'+attribute),None)
    for border in list(style._element.iter(qn('w:pBdr'))):
        border.getparent().remove(border)
normal=document.styles['Normal'];normal.font.size=Pt(12.5)
normal.paragraph_format.line_spacing=1.15;normal.paragraph_format.space_after=Pt(7)
normal.paragraph_format.widow_control=True
for name,size in [('Title',24),('Heading 1',16),('Heading 2',14),('Heading 3',12.5)]:
    style=document.styles[name];style.font.size=Pt(size);style.font.bold=True
    style.paragraph_format.space_before=Pt(12);style.paragraph_format.space_after=Pt(8)
document.styles['Caption'].font.size=Pt(11)
document.styles['Caption'].font.italic=True
footer=section.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');footer._p.append(field)
document.core_properties.title='Xây dựng hệ thống nhận diện biển số phương tiện Việt Nam'
document.core_properties.subject='Báo cáo đồ án Computer Vision phiên bản 1.3.0'
document.core_properties.author='Dự án NhanDienBienSo'
document.core_properties.keywords='YOLO11n CCT OCR camera video temporal consensus FastAPI SQLite'


def p(text='',bold=False):
    paragraph=document.add_paragraph();paragraph.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.add_run(text).bold=bold
    return paragraph


def heading(text,level=2):
    return document.add_heading(text,level)


def page(title,level=2):
    paragraph=heading(title,level);paragraph.paragraph_format.page_break_before=True


def code(text):
    paragraph=document.add_paragraph()
    paragraph.paragraph_format.space_after=Pt(8)
    for index,line in enumerate(text.splitlines()):
        if index: paragraph.add_run().add_break()
        run=paragraph.add_run(line);run.font.name='Consolas';run.font.size=Pt(9)
    return paragraph


def table(headers,rows,widths):
    result=document.add_table(rows=1,cols=len(headers));result.alignment=WD_TABLE_ALIGNMENT.CENTER;result.autofit=False
    properties=result._tbl.tblPr
    borders=OxmlElement('w:tblBorders')
    for edge in ('top','left','bottom','right','insideH','insideV'):
        node=OxmlElement('w:'+edge);node.set(qn('w:val'),'single');node.set(qn('w:sz'),'4');node.set(qn('w:color'),'D9D9D9');borders.append(node)
    properties.append(borders)
    margin=OxmlElement('w:tblCellMar')
    for edge in ('top','bottom','left','right'):
        node=OxmlElement('w:'+edge);node.set(qn('w:w'),'90');node.set(qn('w:type'),'dxa');margin.append(node)
    properties.append(margin)
    repeat=OxmlElement('w:tblHeader');result.rows[0]._tr.get_or_add_trPr().append(repeat)
    for values in [headers]+list(rows):
        row=result.rows[0] if values is headers else result.add_row()
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
        row_index=len(result.rows)-1 if values is not headers else 0
        for index,(cell,text) in enumerate(zip(row.cells,values)):
            cell.width=Cm(widths[index]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            paragraph=cell.paragraphs[0];paragraph.paragraph_format.space_after=Pt(3);paragraph.paragraph_format.space_before=Pt(3);paragraph.paragraph_format.line_spacing=1.05
            paragraph.alignment=WD_ALIGN_PARAGRAPH.LEFT if index==0 else WD_ALIGN_PARAGRAPH.CENTER
            run=paragraph.add_run(str(text));run.font.size=Pt(11)
            shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'E5EBF0' if values is headers else ('F6F7F8' if row_index%2==0 else 'FFFFFF'));cell._tc.get_or_add_tcPr().append(shade)
            if values is headers:run.bold=True
    document.add_paragraph().paragraph_format.space_after=Pt(1)
    return result


def figure(path,caption,width=15.5):
    paragraph=document.add_paragraph();paragraph.alignment=WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.keep_with_next=True
    shape=paragraph.add_run().add_picture(str(path),width=Cm(width))
    shape._inline.docPr.set('descr',caption)
    paragraph=document.add_paragraph(caption,style='Caption');paragraph.alignment=WD_ALIGN_PARAGRAPH.CENTER


def architecture():
    image=Image.new('RGB',(1500,650),'white');draw=ImageDraw.Draw(image)
    font_path=Path('C:/Windows/Fonts/arial.ttf')
    font=ImageFont.truetype(str(font_path),28);small=ImageFont.truetype(str(font_path),23)
    boxes=[(35,90,330,230,'Ảnh camera video','ROI và JPEG 1280'),(600,90,910,230,'YOLO11n','Vùng biển và lớp'),(1160,90,1470,230,'CCT S v2 OCR','Chuỗi và xác suất'),(1160,405,1470,565,'Chất lượng và voting','Khung rõ và track'),(600,405,910,565,'SQLite và ảnh','Lưu một lượt ổn định'),(35,405,330,565,'Giao diện và CSV','Tra cứu và đối chiếu')]
    for x0,y0,x1,y1,title,subtitle in boxes:
        draw.rectangle((x0,y0,x1,y1),outline='#475563',width=3,fill='#F2F5F7')
        draw.text(((x0+x1)/2,y0+40),title,fill='black',font=font,anchor='mm')
        draw.text(((x0+x1)/2,y0+87),subtitle,fill='black',font=small,anchor='mm')
    for start,end in [((330,160),(600,160)),((910,160),(1160,160)),((1315,230),(1315,405)),((1160,485),(910,485)),((600,485),(330,485))]:
        draw.line((start,end),fill='#475563',width=4)
        x,y=end
        points=[(x,y),(x-15,y-9),(x-15,y+9)] if x>start[0] else [(x,y),(x+15,y-9),(x+15,y+9)] if x<start[0] else [(x,y),(x-9,y-15),(x+9,y-15)]
        draw.polygon(points,fill='#475563')
    path=ASSETS/'architecture-current.png';image.save(path);return path


percent=lambda value:f'{value*100:.2f}%'
labels={'original':'Ảnh gốc','synthetic_dark':'Thiếu sáng mô phỏng','synthetic_rain_fog':'Mưa và sương mô phỏng','synthetic_motion_blur':'Mờ ngang 11 pixel','synthetic_night_noise':'Thiếu sáng có nhiễu','synthetic_diagonal_blur':'Mờ chéo 11 pixel','synthetic_rain_blur':'Mưa kết hợp mờ ngang'}

# Cover
title=document.add_paragraph('BÁO CÁO ĐỒ ÁN COMPUTER VISION');title.alignment=WD_ALIGN_PARAGRAPH.CENTER
title.paragraph_format.space_before=Pt(70);title.runs[0].bold=True;title.runs[0].font.size=Pt(16)
title=document.add_paragraph('Xây dựng hệ thống nhận diện biển số phương tiện Việt Nam',style='Title');title.alignment=WD_ALIGN_PARAGRAPH.CENTER
title.paragraph_format.space_before=Pt(40);title.paragraph_format.space_after=Pt(30)
subtitle=document.add_paragraph('Phát hiện vùng biển số và nhận dạng ký tự từ ảnh camera và video',style='Subtitle');subtitle.alignment=WD_ALIGN_PARAGRAPH.CENTER
subtitle.runs[0].font.size=Pt(15)
p('Phiên bản hệ thống 1.3.0',True).alignment=WD_ALIGN_PARAGRAPH.CENTER
p('Ngày hoàn thiện báo cáo 6 tháng 10 năm 2026').alignment=WD_ALIGN_PARAGRAPH.CENTER
p('Dự án NhanDienBienSo').alignment=WD_ALIGN_PARAGRAPH.CENTER
p('Sản phẩm gồm mô hình detector đã huấn luyện, OCR pretrained, API xử lý ảnh, giao diện tra cứu và công cụ vận hành. Phạm vi hiện tại tập trung nhận diện biển số; giao diện quản lý bãi xe đã được loại khỏi sản phẩm.').paragraph_format.space_before=Pt(45)

page('Tóm tắt đồ án',1)
p('Đồ án xây dựng hệ thống nhận diện biển số ô tô và xe máy Việt Nam từ ảnh, camera trình duyệt và file video. Quy trình gồm phát hiện vùng biển bằng YOLO11n, cắt và xử lý biển một hoặc hai dòng, đọc ký tự bằng CCT S v2, đánh giá chất lượng rồi lưu và tra cứu kết quả. Phiên bản 1.3.0 bổ sung gán track theo chuyển động, kiểm chứng kết quả qua nhiều khung, chống bản ghi lặp, chọn vùng nhận diện và sao lưu dữ liệu. Hệ thống chạy cục bộ, có API FastAPI và giao diện tiếng Việt.')
p('Detector được fine-tune trên GPU RTX 3060 Laptop qua 40 epoch nền và 18 epoch bổ sung với dữ liệu train tăng cường. Trên 665 ảnh test, mAP@50 đạt 99,11%, mAP@50–95 đạt 87,50%. Đây là chỉ số định vị vùng biển, không phải tỷ lệ đọc đúng chuỗi. OCR sử dụng trọng số có sẵn và không được huấn luyện trong đồ án. Mẫu 37 biển có thể đọc ở ảnh gốc đạt 37/37 cho cả quy trình; khi mô phỏng mờ ngang mạnh, chỉ 3/37 đọc đúng. Kết quả này chỉ ra chữ bị mất chi tiết vẫn là điểm yếu lớn.')
p('Đánh giá bổ sung trên ba video thật công khai: năm mục tiêu chọn trong cảnh giao thông ban ngày và một biển xe máy trong nhà được đọc ổn định; cảnh giao thông đêm có hai trong ba biển ô tô đã chọn ổn định. Biển thứ ba đọc đúng ở một số khung nhưng không đủ quan sát rõ thống nhất. Các clip cũng được dùng kiểm tra và sửa gán track, nên là bộ hồi quy phát triển, chưa phải tập nghiệm thu độc lập. Không có video mưa thật hoặc camera triển khai của người dùng để công bố chất lượng hiện trường.')
p('Sản phẩm đã có quy trình chạy, kiểm thử, sao lưu và khôi phục; phù hợp triển khai thử nghiệm có người đối chiếu trong phạm vi một máy và lưu lượng nhỏ. Để nghiệm thu vận hành dài hạn, cần dữ liệu theo camera và ngày quay, nhãn mọi lượt xe, phép đo độ trễ và các thử lỗi mạng, mất điện, lóa, mưa cùng tải liên tục. Đồ án không tự động quyết định quyền nhận xe hoặc mở barrier.')
p('Từ khóa YOLO11n OCR CCT S v2 nhận diện biển số kiểm chứng thời gian FastAPI SQLite',True)

document.add_page_break();document.add_paragraph('Mục lục',style='Title')
paragraph=document.add_paragraph();field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'TOC \\o "1-1" \\h \\z \\u');paragraph._p.append(field)
p('Các bảng và hình được đặt ngay cạnh phần phân tích. Phụ lục cuối báo cáo chỉ dẫn mã nguồn, giao thức API và cách tái tạo kết quả.')

page('Chương 1 Tổng quan đề tài',1)
heading('Bài toán và động cơ thực hiện')
p('Nhận diện biển số tự động chuyển nội dung trong khung ảnh thành chuỗi ký tự có thể tìm kiếm. Ảnh đầu vào chứa nhiều thành phần như phương tiện, người, nền, đèn và chữ khác; hệ thống phải tìm đúng vùng biển trước khi đọc chữ. Điều kiện ghi hình làm bài toán khó hơn: thiếu sáng giảm tương phản, mưa hoặc sương làm nhạt cạnh, chuyển động gây nhòe và góc nhìn làm biến dạng ký tự. Hai bước phát hiện và đọc ký tự cần được đánh giá riêng để tránh kết luận sai từ một chỉ số chung.')
p('Mục tiêu của đồ án là một sản phẩm có thể chạy, tra cứu và kiểm chứng được: có trọng số detector, API, giao diện ảnh/camera/video, bằng chứng ảnh và báo cáo số liệu. Chuỗi dự đoán luôn cần đi kèm ngữ cảnh và cảnh báo khi ảnh không đủ rõ. Việc biển số đúng mẫu ký tự Việt Nam chỉ là kiểm tra cú pháp, không xác minh biển đã đăng ký hoặc danh tính chủ xe.')
heading('Yêu cầu và sản phẩm bàn giao')
table(['Yêu cầu','Sản phẩm thực hiện'],[
 ('Phát hiện biển số','YOLO11n fine-tune với hai lớp biển dài và biển vuông'),
 ('Nhận dạng ký tự','CCT S v2 pretrained và xử lý biển hai dòng'),
 ('Ảnh camera video','Giao diện xử lý ảnh và khung lấy mẫu; CLI USB RTSP video'),
 ('Tra cứu kết quả','SQLite, ảnh nguồn/crop, bộ lọc thời điểm và CSV'),
 ('Vận hành','Voting, chống lặp, ROI, backup verify và retention dry-run'),
 ('Báo cáo và lưu trữ','DOCX cập nhật, báo cáo JSON, mã nguồn và GitHub')],[5.1,11.1])
heading('Phạm vi hiện tại')
p('Giao diện quản lý bãi xe không còn trong phạm vi. API và bằng chứng bãi xe từ phiên bản cũ được giữ để không phá dữ liệu; đây không phải chức năng mới được bàn giao trên giao diện. Hệ thống chưa có phân quyền nhiều người, tính phí, RFID, nhận diện khuôn mặt hay điều khiển thiết bị cổng. Mọi lệnh và file của dự án nằm tại D:\\ComputerVision\\NhanDienBienSo, tách khỏi các dự án khác trong ComputerVision.')

page('Chương 2 Cơ sở lý thuyết',1)
heading('Phát hiện đối tượng và YOLO11n')
p('Phát hiện đối tượng tìm vị trí và lớp của một đối tượng trong ảnh. Đầu ra thường gồm hộp bao, nhãn và điểm tin cậy. YOLO là họ detector một giai đoạn, suy luận trực tiếp từ đặc trưng ảnh. Đồ án dùng biến thể nhỏ YOLO11n để giảm chi phí tính toán trên GPU laptop. Tài liệu chính thức mô tả YOLO11 và cách train, val, predict; không có bài báo riêng chính thức cho YOLO11 [1].')
p('Cấu hình thư viện đang cài sử dụng các khối Conv, C3k2, SPPF và C2PSA, kết hợp đặc trưng nhiều tỷ lệ ở head P3, P4, P5. Backbone trích đặc trưng, neck ghép thông tin từ các mức kích thước, head dự đoán vị trí và lớp. Input detector là 640 pixel theo cơ chế resize/letterbox của Ultralytics. Các hộp được ánh xạ về ảnh đầu vào để cắt OCR. Hai lớp của dự án là plate_long và plate_square; chọn cách xử lý hai dòng dựa trên lớp và tỷ lệ crop.')
heading('Hộp bao và IoU')
p('Một hộp được biểu diễn bằng hai góc (x0, y0, x1, y1). IoU đo mức giao nhau giữa hộp dự đoán và hộp nhãn, bằng diện tích phần giao chia diện tích phần hợp. IoU bằng 1 khi hộp trùng hoàn toàn và bằng 0 khi không giao nhau. Trong phép matching của kiểm tra điều kiện khó, một dự đoán chỉ khớp một nhãn cùng lớp khi IoU ít nhất 0,5; từng nhãn chỉ được dùng một lần.')
code('IoU(A, B) = area(A intersection B) / area(A union B)')
p('Non maximum suppression loại các hộp trùng nhiều theo cấu hình detector. Ngưỡng confidence 0,35 được giữ cho các phép stress/video hiện tại. Giảm ngưỡng có thể tăng recall nhưng cũng tăng false positive. Không chọn lại ngưỡng bằng kết quả test để làm đẹp số liệu.')
heading('Hàm mất mát và transfer learning')
p('Huấn luyện tối ưu lỗi vị trí, phân lớp và biểu diễn phân bố khoảng cách hộp của detector. Thư viện cung cấp triển khai loss và optimizer; đồ án sử dụng trực tiếp thay vì tự viết. Transfer learning khởi tạo từ trọng số YOLO11n pretrained rồi fine-tune trên biển số Việt Nam. Batch là số ảnh trong một bước cập nhật, epoch là một lượt qua dữ liệu train. Validation dùng chọn checkpoint; test dùng báo cáo sau khi đã chốt lựa chọn.')

page('Nhận dạng ký tự và xử lý crop')
p('OCR nhận một ảnh biển đã cắt và trả chuỗi ký tự. Sai ở detector có thể làm mất ký tự ngoài crop; ngay cả crop đúng vị trí vẫn có thể không đọc được do mờ hoặc lóa. Vì vậy, tỷ lệ OCR trên crop nhãn và tỷ lệ đúng cả detector cộng OCR là hai phép đo khác nhau. Đồ án giữ phép đo cả hai để xác định nơi phát sinh lỗi.')
p('CCT là kiến trúc Compact Convolutional Transformer: dùng đặc trưng từ convolution trước khi xử lý bằng transformer để biểu diễn quan hệ giữa các đặc trưng. Nghiên cứu Compact Transformers trình bày convolutional tokenization và sequence pooling [2]. Trong dự án, trọng số OCR cụ thể là cct_s_v2_global_model của FastPlateOCR [3]; cấu hình có ảnh RGB 128 × 64, tối đa 10 vị trí ký tự và bảng chữ số/chữ Latin cùng ký tự padding. Không suy diễn rằng checkpoint này được huấn luyện trên dữ liệu của đồ án.')
heading('Biển một dòng và hai dòng')
p('Mỗi hộp được nới khoảng 3,5% theo hai chiều và chặn tại biên ảnh. OCR thử crop gốc; với biển vuông hoặc tỷ lệ rộng/cao thấp hơn 2,2, hệ thống còn ghép hai dòng thành một dòng. Đường chia nằm trong 35–65% chiều cao và được chọn bằng vùng có ít nét đen nhất theo phép chiếu ngang. Hai phần được resize cùng chiều cao và nối bằng khoảng trắng. Cách này phù hợp biển gần thẳng; không thay thế nắn phối cảnh bằng keypoint khi nghiêng mạnh.')
p('CLAHE trên kênh sáng của ảnh được thử thêm để cải thiện tương phản cục bộ. Những biến thể này cung cấp nhiều cách đọc của cùng crop, không phải nhiều bằng chứng độc lập. Chuỗi được viết hoa và bỏ ký tự không phải chữ số hoặc chữ Latin. Mẫu dân dụng phổ biến được kiểm tra bằng regex; đây là kiểm tra định dạng vận hành chứ không bao phủ mọi biển quân đội, ngoại giao hoặc biển đặc biệt.')
heading('Điểm tin cậy và mâu thuẫn OCR')
p('Điểm OCR là trung bình xác suất ký tự trong chuỗi sau chuẩn hóa. Hệ thống chọn ứng viên theo tính hợp lệ định dạng rồi theo điểm OCR. Nếu các ứng viên hợp lệ khác chuỗi, ocr_disagreement bật cờ cần kiểm tra. Điểm 100% là điểm của model, không chứng minh toàn bộ biển đúng; nhiều cách xử lý có thể đưa ra các chuỗi khác nhau với điểm cao. Người dùng cần xem ảnh nguồn khi cờ này xuất hiện.')

page('Chất lượng ảnh và kiểm chứng theo thời gian')
p('Độ sáng crop là giá trị xám trung bình. Độ chi tiết được ước lượng bằng phương sai Laplacian sau khi chuẩn hóa kích thước crop. Các ngưỡng mặc định là độ sáng 40 và độ chi tiết 25; biển có cạnh dưới 24 pixel theo chiều cao hoặc 48 theo chiều rộng cũng bị cảnh báo. Đây là heuristic cần hiệu chỉnh theo camera, không phải xác suất ký tự có thể đọc được. Texture nền, phản xạ hoặc nhiễu có thể làm điểm nét cao dù chữ khó đọc.')
heading('Lựa chọn khung rõ hơn')
p('Camera trình duyệt thử ba khung cách khoảng 33 ms và giữ khung có chi tiết toàn ảnh cao hơn. Chi tiết toàn ảnh có thể ưu tiên nền; vùng nhận diện giúp giới hạn phép lấy ảnh tới khu vực xe đi qua. Nếu cả ba đều nhòe thì lựa chọn tốt nhất vẫn có thể không đọc được. Tăng tần suất không khôi phục thông tin đã mất; nên cải thiện ghi hình và tận dụng thời điểm xe chậm hơn.')
heading('Gán track và bỏ phiếu')
p('Hộp được chuẩn hóa theo chiều rộng/cao để tránh thay đổi tỷ lệ tọa độ. Với mỗi track, vận tốc bốn tọa độ được ước lượng từ hai lần quan sát gần nhất; vị trí tiếp theo được dự đoán tuyến tính. Ghép dùng giá trị IoU lớn hơn giữa hộp cũ và hộp dự đoán. Cần score ít nhất 0,2 và nếu có hai ứng viên thì chênh lệch ít nhất 0,15. Ghép mơ hồ tạo track mới để hạn chế trộn hai xe; mỗi track chỉ được ghép một lần trong một khung.')
code('predicted_box = previous_box + velocity * elapsed_seconds\nstable = same_clear_reads >= 3 and same_clear_reads / observations >= 0.6')
p('Mỗi track giữ tối đa bảy quan sát; quan sát needs_review không góp phiếu tốt nhưng vẫn nằm trong mẫu số. Ít nhất ba lần đọc rõ cùng chuỗi, chiếm ít nhất 60%, và khung hiện tại rõ/đồng ý với chuỗi đó mới có trạng thái stable. Track vắng quá 2,5 giây hết hạn. Các khung có thể quay lại review sau một kết quả stable; không ép cả đoạn video luôn đúng. Voting ở đây là thuật toán của dự án; không phải triển khai nguyên xi phương pháp Character Time-series Matching trong tài liệu tham khảo [4].')
p('Voting giảm dao động nhưng có thể cùng thống nhất một lỗi OCR; xe xuất hiện rất ngắn có thể không kịp đủ ba lần đọc. Track chỉ biểu diễn sự liên tục hình ảnh, không phải danh tính phương tiện. Chống lặp văn bản chỉ dùng khi ghi sự kiện, không dùng làm khóa ghép track.')

page('Chương 3 Dữ liệu và huấn luyện',1)
heading('Nguồn dữ liệu và chuẩn bị nhãn')
p('Dữ liệu lấy từ Vietnam License Plate Segment Datasets của hoanglvuit, ghim revision b8a1e809cadea0e53b1c519f637d494f0d87796f [5]. File archive có SHA-256 được kiểm tra trong prepare_data.py trước khi tạo split. Polygon chuẩn hóa được đổi thành hộp min/max và kiểm tra lớp, số tọa độ, giá trị hữu hạn trong [0,1], hộp có diện tích dương. Các nhãn không hợp lệ được ghi vào manifest thay vì âm thầm nhận vào train.')
p('Ảnh được loại trùng theo hash pixel RGB; 44 ảnh trùng được bỏ, sáu mẫu nhãn bị từ chối. Các ảnh còn lại được chia theo nhóm gần đúng từ tiền tố tên và khối thứ tự 25 ảnh, dùng seed 42. Cách nhóm tốt hơn chia ngẫu nhiên từng ảnh liền kề, nhưng không có camera hoặc vehicle ID nên không thể chứng minh biển cùng một xe không xuất hiện ở nhiều split.')
table(['Tập dữ liệu','Số ảnh','Vai trò'],[('Train gốc','3.189','Cập nhật trọng số'),('Validation','674','Chọn checkpoint và kiểm tra tiêu chí'),('Test','665','Đánh giá hồi quy sau khi chốt model'),('Train tăng cường','3.189','Chỉ biến đổi ảnh train')],[4.7,3,8.5])
p('Tập train fine-tune bổ sung gồm 6.378 lượt ảnh: 3.189 ảnh gốc và 3.189 ảnh tăng cường. Validation và test giữ nguyên ảnh nguồn. Các file data.yaml và train.txt đã được cập nhật đường dẫn sau khi chuyển vào NhanDienBienSo. File ZIP tải về đã được dọn khi bộ dữ liệu xử lý đầy đủ còn tồn tại; nguồn revision/hash vẫn cho phép tải lại.')
heading('Tính tái lập và giới hạn dữ liệu')
p('dataset.json giữ nguồn, hash, nhóm, split và các mẫu bị loại. Mẫu OCR gồm 40 ảnh chọn trước dự đoán, phiên âm bằng mắt; ba ảnh quá mờ hoặc che được ghi loại và 37 mẫu còn lại dùng xuyên suốt các điều kiện mô phỏng. Có sửa nhãn sau kiểm tra phóng to; chưa có người thứ hai kiểm tra độc lập. Vì vậy, độ chính xác OCR của nhóm mẫu này cần được hiểu trong đúng giới hạn chọn mẫu.')

page('Cấu hình huấn luyện và tăng cường dữ liệu')
p('Giai đoạn nền khởi tạo từ yolo11n.pt và huấn luyện 40 epoch trên RTX 3060 Laptop 6 GB, input 640, batch 16. Model tốt nhất theo validation được lưu lại. Giai đoạn bổ sung tiếp tục từ detector nền trong 18 epoch; không huấn luyện OCR. Thời gian ghi trong JSON lần lượt khoảng 29,9 phút và 28,7 phút; lượt bổ sung gồm chuẩn bị tăng cường và train, không bao gồm mọi phép đánh giá sau train.')
table(['Tham số','Fine tune bổ sung'],[('Optimizer','AdamW'),('lr0 và lrf','0,0003 và 0,1'),('Seed','73'),('Input và batch','640 và 16'),('Workers','2'),('Mosaic','0,2; tắt bốn epoch cuối'),('Lật ảnh','Không lật ngang hoặc dọc ký tự'),('Checkpoint chọn','best theo validation')],[6.5,9.7])
p('AdamW kết hợp cập nhật thích nghi với weight decay tách khỏi bước gradient. Learning rate quyết định độ lớn bước cập nhật; lr0 thấp giúp tiếp tục từ model nền thay vì làm thay đổi quá mạnh ngay đầu lượt. Cấu hình đầy đủ nằm trong hyperparameters của training.json, không chỉ bảng tóm tắt này. Đồ án không tự đề xuất kiến trúc YOLO mới hoặc sửa thuật toán optimizer.')
p('Tăng cường chia theo seed: 1.914 ảnh mờ chuyển động nhiều hướng, trong đó có một phần kết hợp tối; 638 ảnh thiếu sáng có nhiễu; 637 ảnh mưa/sương. Kernel đường thẳng dài 5, 7, 9, 11 hoặc 13 pixel được chuẩn hóa trước khi convolution. Thiếu sáng áp dụng gamma/gain và nhiễu; mưa kết hợp lớp sương và các vệt sáng. Biến đổi không thay tọa độ hình học nên nhãn hộp giữ nguyên. Đây là mô phỏng, không đại diện đầy đủ giọt nước trên kính, IR hoặc lóa đèn thật.')
page('Diễn biến loss và validation qua các epoch')
chart=Image.open(REPORTS/'results.png')
panel=Image.new('RGB',(960,1200),'white')
for destination,box in [((0,0),(0,0,480,600)),((480,0),(0,600,480,1200)),((0,600),(1440,600,1920,1200)),((480,600),(1920,600,2400,1200))]:
    panel.paste(chart.crop(box),destination)
panel.save(ASSETS/'training-panels-current.png')
figure(ASSETS/'training-panels-current.png','Hình 1 Loss train validation và mAP của 18 epoch fine tune bổ sung',14.7)
p('Bốn panel được trích từ results.png của đúng lượt fine tune bổ sung. Trục ngang là epoch; các đường loss và mAP mô tả diễn biến học và validation. Số liệu từng epoch nằm trong training_curve.csv. Checkpoint vẫn được chọn theo protocol validation, không chọn một epoch bằng hình test.')

page('Chọn checkpoint và quy trình đánh giá')
p('Trước test, best và last được so trên cùng 200 ảnh validation cùng ngưỡng/IoU. Điều kiện chọn đặt trước: recall mờ tăng ít nhất ba điểm phần trăm; mAP50–95 gốc giảm không quá 1,5 điểm; recall từng điều kiện giảm không quá một điểm; precision từng điều kiện ít nhất 95%. Cả hai đạt tiêu chí; recall mờ đều 226/226 nên chọn best khi đồng hạng. Chỉ sau đó mới đo test và xuất các báo cáo kết quả.')
p('Giới hạn quan trọng là test của phiên bản nền đã được xem khi chẩn đoán điểm yếu chuyển động. Lượt đánh giá sau đó là benchmark hồi quy, không còn là test hoàn toàn chưa quan sát trong quá trình phát triển. Không dùng kết quả test để chọn best/last hay đổi confidence của lượt fine-tune, nhưng vẫn phải tạo tập độc lập theo camera/ngày quay để đánh giá tổng quát hóa.')
heading('Các chỉ số sử dụng')
table(['Chỉ số','Định nghĩa'],[('Precision','TP / (TP + FP)'),('Recall','TP / (TP + FN)'),('mAP@50','Trung bình AP các lớp tại IoU 0,5'),('mAP@50–95','Trung bình AP các lớp và IoU 0,50 đến 0,95'),('Exact match OCR','Tỷ lệ chuỗi đúng hoàn toàn'),('CER','(Thay thế + Xóa + Chèn) / Số ký tự nhãn'),('Đọc ổn định video','Mục tiêu chọn có ít nhất một kết quả stable đúng')],[5.2,11])
p('AP tổng hợp đường precision/recall qua nhiều ngưỡng, khác phép matching tại confidence cố định. Các precision/recall Ultralytics trên toàn test cũng dùng cách tổng hợp riêng; không đánh đồng với bảng stress dùng matching một-một ở 0,35. CER cho biết lượng lỗi ký tự dù chuỗi không đúng hoàn toàn, còn exact match phù hợp nhu cầu tìm biển đúng từng ký tự.')
p('Video chưa gán nhãn mọi xe hoặc mọi frame nên chỉ báo cáo độ bao phủ mục tiêu chọn. Không tính precision toàn cảnh, không lấy số dòng CSV làm số xe và không gọi tỷ lệ 5/5 của nhóm mẫu là độ chính xác phổ quát. Các số FPS suy luận cũng không thay cho FPS camera hoặc độ trễ từ lúc xe xuất hiện đến sự kiện ổn định.')

page('Chương 4 Thiết kế và hiện thực hệ thống',1)
figure(architecture(),'Hình 2 Luồng ảnh camera video đến kết quả ổn định và lịch sử',16)
p('Mã nguồn gồm recognition.py chứa decode/model/OCR/chất lượng, temporal.py chứa trạng thái theo phiên, app.py cung cấp API và lưu dữ liệu, web/ chứa giao diện, scripts/ chứa train/evaluate/camera/maintenance. Không thêm framework frontend; dùng HTML, CSS và JavaScript có sẵn trong trình duyệt. SQLite phù hợp máy đơn và triển khai nhỏ, giảm yêu cầu cài dịch vụ cơ sở dữ liệu riêng.')
heading('Luồng yêu cầu xử lý ảnh')
p('API kiểm tra Content-Length và giới hạn upload, đọc tối đa 10 MB cộng một byte để phát hiện quá giới hạn, giải mã JPG/PNG/WebP bằng Pillow, xử lý orientation EXIF và chặn ảnh dưới 32 pixel hoặc vượt 16 triệu pixel. Sau decode, detector trả crop và OCR/chất lượng. Ảnh đơn giữ hành vi xử lý một lần; camera/video thêm bộ phiên thời gian trước quyết định lưu. Lỗi decode trả 400, model chưa sẵn sàng trả 503; dữ liệu form không hợp lệ trả 422.')
p('Một khóa inference bảo đảm GPU nhỏ không bị nhiều request cùng chạy model. Camera trình duyệt chỉ gửi một request tại một thời điểm; sau xử lý lấy khung mới và bù thời gian còn lại của chu kỳ. File video được seek/lấy mẫu tuần tự và có thể xử lý chậm hơn thời gian thực. Timeout phía UI/CLI là 30 giây; nếu API không phản hồi, dừng và thông báo để người dùng kiểm tra thay vì xếp hàng vô hạn.')

page('Giao thức phiên và lưu trữ dữ liệu')
table(['Trường form','Ý nghĩa'],[('file','Ảnh JPEG PNG WebP'),('source','Nguồn và mốc video phục vụ tra cứu'),('confidence','Ngưỡng detector trong giới hạn API'),('save','Có lưu dữ liệu của lượt hợp lệ hay không'),('stream_id','UUID mới khi bắt đầu hoặc quét lại camera video'),('sample_time','Giây tăng dần trong phiên; gửi cùng stream_id')],[5,11.2])
p('Phiên nhận diện giữ track, bảy quan sát gần nhất, các biển đã lưu gần đây và phản hồi khung cuối. Replay cùng mốc và chữ ký ảnh/nguồn/ngưỡng trả lại request_id cũ, không suy luận hoặc lưu lại. Gửi mốc cũ hay ảnh khác ở mốc đã dùng trả 409. Phiên tối đa 128, nhàn rỗi hết hạn sau mười phút; track lưu tối đa 40. Do trạng thái ở RAM, API cần một worker. Khi khởi động lại, chống lặp đặt lại nhưng lịch sử SQLite không mất.')
p('Bản ghi chỉ được lưu khi save=true và là sự kiện stable chưa lưu của cùng biển/track, đồng thời không có cùng biển đã lưu trong 30 giây của phiên. Ảnh đơn không có stream_id vẫn lưu từng request như trước. Khung source và crop có ID UUID riêng; nhiều biển trong cùng khung dùng chung ảnh nguồn. Các file được dọn nếu transaction lỗi. Trạng thái phiên được rollback khi xử lý/lưu thất bại để lần thử tiếp theo không mất cơ hội ghi sự kiện.')
heading('Cấu trúc cơ sở dữ liệu')
p('records giữ id, created_at UTC, source, chuỗi/display, điểm detector/OCR, needs_review, bbox và image_id/crop_id. review_details mới giữ chất lượng, bất đồng OCR, hợp lệ định dạng và tóm tắt temporal để giải thích cảnh báo sau này. Migration thêm cột bằng ALTER TABLE khi chưa tồn tại; dữ liệu cũ nhận giá trị rỗng và không bị sửa ký tự. Các ảnh còn liên kết với parking_sessions cũ vẫn được bảo vệ trước thao tác xóa lịch sử.')
p('Giao diện hiển thị giờ Việt Nam UTC+7, CSV/API dùng UTC. CSV escape các giá trị có thể bị phần mềm bảng tính hiểu là công thức. API ảnh tra cứu kiểm tra quyền bằng X-API-Key; giao diện lấy blob có header, không nhúng key vào URL. Ảnh và dữ liệu vận hành được loại khỏi Git.')

page('Chương 5 Kết quả thực nghiệm',1)
heading('Detector trên tập test gốc')
base=hardening['baseline']['training']['test']
keys=[('metrics/mAP50(B)','mAP@50'),('metrics/mAP50-95(B)','mAP@50–95'),('metrics/precision(B)','Precision tổng hợp'),('metrics/recall(B)','Recall tổng hợp')]
table(['Chỉ số','Nền 40 epoch','Sau fine tune'],[(label,percent(base[key]),percent(training['test'][key])) for key,label in keys],[6.2,4.9,5.1])
p('Đánh giá gồm 665 ảnh và 796 biển có nhãn. mAP@50 tăng nhẹ, mAP50–95 giảm nhẹ; fine-tune không làm tốt hơn mọi tiêu chí ảnh gốc. Trọng số giữ nguyên trong lượt phát triển vận hành 1.3.0. Health API trả hash của model đang dùng trong RAM, đã được đối chiếu với hash báo cáo sau khi restart.')
figure(REPORTS/'confusion_matrix_normalized.png','Hình 3 Ma trận nhầm lẫn chuẩn hóa từ đánh giá test detector',12.5)
p('Biển một và hai dòng được đánh giá theo hai lớp, nhưng mọi chuỗi ký tự vẫn do OCR đọc sau crop. Ma trận và mAP chỉ mô tả detector. Không sử dụng 99,11% mAP@50 để quảng bá rằng 99,11% xe sẽ được đọc đúng cả biển tại camera thực tế.')

page('Kết quả mô phỏng điều kiện khó')
table(['Điều kiện','Recall nền','Recall mới','Precision mới'],[(labels[name],percent(stress['baseline']['conditions'][name]['recall_at_iou50']),percent(item['recall_at_iou50']),percent(item['precision_at_iou50'])) for name,item in stress['current']['conditions'].items()],[6.3,3.3,3.3,3.3])
p('Bảng dùng cùng 200 ảnh test với 230 biển, confidence 0,35 và IoU ít nhất 0,5, matching cùng lớp một-một. Mờ ngang cải thiện 16,96 điểm phần trăm, mờ chéo cải thiện 50,87 điểm, mưa kèm mờ cải thiện 20,87 điểm. Recall gốc, thiếu sáng và mưa đơn giảm nhẹ trên nhóm ảnh này. Những biến đổi bổ sung được đo sau khi model đã chốt; không đổi model/ngưỡng để tối ưu từng dòng kết quả.')
heading('OCR và toàn quy trình')
table(['Điều kiện','Crop OCR đúng','Pipeline đúng','CER crop'],[(labels[name],f"{round(item['exact_match']*item['samples'])}/{item['samples']}",f"{round(item['pipeline_exact_match']*item['samples'])}/{item['samples']}",percent(item['character_error_rate'])) for name,item in weather['conditions'].items()],[6.3,3.3,3.3,3.3])
p('Giữ cùng 37 mẫu nguồn đọc được ở ảnh gốc, không loại thêm mẫu sau biến đổi. Mờ ngang mạnh làm pipeline chỉ đọc đúng 3/37 dù detector vẫn có recall cao. Convolution làm mất cạnh ký tự; ghép dòng và tăng tương phản không tái tạo chắc chắn thông tin đã mất. Đây là lý do hệ thống cần cờ kiểm tra và lấy khung rõ, không dùng thuật toán làm nét để tự bịa chuỗi.')
p('37/37 ở ảnh gốc/tối/mưa mô phỏng là kết quả trên mẫu nhỏ thiên lệch đọc được. Thiếu sáng mô phỏng không thay phổ IR, mưa giả không mô phỏng đầy đủ nước bám kính và đèn phản xạ. Những phép này là thử độ bền của model, chưa chứng minh đọc chữ dưới mọi điều kiện hiện trường.')

page('Đánh giá trên video thật công khai')
p('Ba clip nguồn được tải theo URL ghim revision và kiểm tra SHA-256: video giao thông có xe di chuyển ban ngày, clip camera cầm tay trước xe máy đỗ trong nhà và clip giao thông đêm xám. Năm, một và ba mục tiêu đọc được bằng mắt đã được ghi trước inference. Các clip có nguồn và nhãn trong video_ground_truth.json; file video không phát hành trên Git [6][7]. Các nhãn chưa được người khác kiểm tra độc lập và chưa bao phủ mọi xe trong cảnh.')
rows=[]
for clip in video['clips']:
    label='Ban ngày có xe di chuyển' if clip['file']=='moving-car.MOV' else 'Xe máy trong nhà' if clip['file']=='video1.mp4' else 'Đêm ROI định trước' if clip['roi_percent'] else 'Đêm toàn khung'
    rows.append((label,clip['sampled_frames'],f"{len(clip['targets_read_in_any_frame'])}/{len(clip['selected_targets'])}",f"{len(clip['targets_read_stably'])}/{len(clip['selected_targets'])}"))
table(['Clip','Khung','Đúng một khung','Đúng ổn định'],rows,[6.3,2.3,3.8,3.8])
p('Lấy mẫu 5 Hz, cạnh dài tối đa 1280, JPEG quality 90, detector input 640 FP32, cùng OCR và ngưỡng 0,35. Lượt đầu camera cầm tay có 18 khung, cảnh ban ngày 140 khung, cảnh đêm 90 khung. ROI đêm định trước là x0 y15 rộng50 cao80% và được đo riêng. Phép thử ROI không tăng số mục tiêu stable, đồng thời có thêm một chuỗi stable ngoài danh sách mục tiêu chưa xác minh. Không lựa chọn ROI này làm mặc định tối ưu cho mọi camera.')
p('Biển 65A18114 trong clip đêm được OCR đúng ở nhiều khung nhưng các biến thể còn bất đồng nên thiếu ba lần đọc rõ thống nhất. Hệ thống giữ review và không tự chấp nhận. Một lỗi association với xe tiến nhanh được tìm thấy qua clip ban ngày và sửa bằng dự đoán vận tốc. Do đó các clip là dữ liệu phát triển/hồi quy, không phải test mù độc lập; chưa biết mức trùng nguồn với bộ train ảnh.')
heading('Hiệu năng và độ trễ')
table(['Clip','Pipeline TB ms','Pipeline p95 ms','Toàn phép đo s'],[(row[0],clip['pipeline_mean_ms'],clip['pipeline_p95_ms'],clip['processing_seconds']) for row,clip in zip(rows,video['clips'])],[6.3,3.3,3.3,3.3])
p('Pipeline TB/p95 chỉ tính engine.predict, không gồm toàn bộ seek, decode, JPEG, HTTP và ghi ảnh. Có một blank warmup detector; OCR lần đầu vẫn nằm trong phép đo. Full elapsed có phần giải mã và lấy mẫu, không tương đương stream camera thời gian thực. Tăng FPS mục tiêu không bảo đảm đạt FPS xử lý nếu có nhiều biển trong cùng khung.')

page('Kiểm thử phần mềm và độ an toàn dữ liệu')
p('Kiểm thử phần mềm tách khỏi độ chính xác model. Inference giả cho phép tái lập trạng thái lưu/xóa, xác thực và race mà không phụ thuộc cảnh ảnh; API thật với ảnh/video kiểm tra tích hợp model. Hiện chín unittest và hai bộ điều khiển Node đã chạy đạt. Workflow GitHub chạy trên CPU để kiểm tra hợp đồng phần mềm, không tự huấn luyện lại hoặc tự tạo benchmark camera.')
table(['Nhóm kiểm thử','Kết quả được xác minh'],[
 ('Upload và biên dữ liệu','Ảnh sai định dạng, quá kích thước, confidence NaN bị chặn'),
 ('Auth và CSV','API key sai bị từ chối; công thức CSV được escape'),
 ('Lịch sử và bằng chứng cũ','Lưu tìm xóa đúng; giữ ảnh đang tham chiếu bãi xe'),
 ('Quality và OCR','Điểm cao vẫn review khi mờ hoặc bất đồng'),
 ('Temporal','Dao động ký tự, track hai xe, xe nhanh, gap và phiên riêng'),
 ('Replay và chống lặp','100 khung cùng track không thêm lượt sau cooldown'),
 ('Backup và retention','Đủ SQLite/ảnh/hash; backup hỏng bị phát hiện; giữ bằng chứng'),
 ('Camera và video JS','Cancellation, lấy mẫu, ROI kích thước và gộp stable')],[5.7,10.5])
p('API thật nhận tám khung cùng biển với save=false, trả pending rồi stable, không tăng lịch sử. MP4 trên trình duyệt xử lý 18 khung và gộp một lượt stable 59V184625; tốc độ quan sát 3,3 lượt/s, không phải FPS camera. Khung sau vẫn có thể cần kiểm tra; bảng stable giữ khung đã đủ điều kiện trước đó. Chỉ coi dữ liệu model là tín hiệu đối chiếu, không tự đánh giá danh tính hoặc quyền sở hữu phương tiện.')
p('Snapshot vận hành có 60 bản ghi và 86 ảnh. Backup verify đạt; khôi phục thử vào thư mục riêng, SQLite integrity_check trả ok và số bản ghi là 60. Dry-run retention 30 ngày có 0 lượt đủ điều kiện; không thực hiện xóa lịch sử người dùng. Backup nằm cục bộ, không đẩy ảnh dữ liệu vận hành lên GitHub. API sau migration vẫn giữ 60 bản ghi.')

page('Chương 6 Giao diện và vận hành',1)
figure(ASSETS/'stream-result.png','Hình 4 Khung stable và bảng gộp một lượt biển từ MP4 thật',12.6)
p('Giao diện hiện còn Nhận diện, Lịch sử ảnh và Mô hình. Ảnh/video/camera cùng dùng endpoint xử lý ảnh; video có tạm dừng, tiếp tục, quét lại và xem mốc đầu của lượt stable. Bảng giữ 100 lượt gần nhất; CSV chứa mọi lượt stable đã phân tích. Cảnh báo kết quả cuối khung và bảng lượt stable là hai thông tin khác nhau: khung hiện tại xấu hơn không xóa bằng chứng stable trước đó.')

page('Quy trình dùng camera và video')
p('Bắt đầu bằng ảnh rõ để kiểm tra health/model. Với camera, cấp quyền tại localhost hoặc HTTPS rồi quan sát hình trực tiếp và khung đã phân tích riêng. Hình trực tiếp yêu cầu 30 FPS, còn mục tiêu nhận diện mặc định 5 lượt/s, chỉnh 1/2/5/10. UI đo tần suất phản hồi thực đạt; không cộng thêm ba giây sau mỗi lần xử lý. Khi đổi tab, dừng stream; không cập nhật phản hồi cũ vào giao diện đã chuyển nguồn.')
p('Video giới hạn 500 MB và mười phút theo luồng trình duyệt, dùng MP4/WebM/OGV đọc được bởi codec trình duyệt. Video gốc được giải mã tại máy dùng giao diện; chỉ JPEG từng khung gửi server. Muốn nhận diện video dài hoặc codec không được browser hỗ trợ, dùng camera.py với nguồn file. Khi save=true, backend vẫn chỉ ghi lượt stable; replay cùng stream/mốc không nhân bản bản ghi. Pause không hủy một request đã tới server, nên nếu đã cho phép lưu thì request đang xử lý có thể hoàn tất ghi.')
heading('Hiệu chỉnh vùng nhận diện')
p('Mục Vùng nhận diện cho nhập x, y, rộng, cao theo phần trăm từ góc trên trái. Tất cả phải nằm trong 0–100% và rộng/cao dương; giao diện chặn ví dụ x80 rộng100. Áp dụng dừng camera và bắt đầu lại video/UUID để không ghép tọa độ của hai vùng khác nhau. Crop trước resize giúp detector dành nhiều pixel hơn cho làn cần quan sát, nhưng làm mất ngữ cảnh toàn ảnh. Ảnh bằng chứng là vùng đã cắt; cần chọn vùng bao trọn mọi vị trí biển mong muốn.')
code('.\\.venv\\Scripts\\python.exe scripts\\camera.py --source 0 --fps 5 --save\n.\\.venv\\Scripts\\python.exe scripts\\camera.py --source video.mp4 --roi "0,15,50,80"')
p('CLI cho phép webcam số, file video hoặc RTSP. Buffer/FPS thuộc driver nên cần đo tại thiết bị triển khai; công cụ chưa được thử live USB/RTSP hoặc reconnect dài hạn. Không in địa chỉ camera chứa mật khẩu vào báo cáo hay Git. Khi camera/file đọc hết hoặc lỗi, CLI kết thúc; giám sát và reconnect tự động chưa được nghiệm thu.')
heading('Xử lý kết quả cần kiểm tra')
p('Lý do có thể là thiếu sáng, mờ/ít chi tiết, biển nhỏ, OCR confidence thấp, không hợp mẫu cú pháp hoặc bất đồng biến thể. Bản ghi mới lưu các lý do này; bản ghi cũ có thể thiếu chi tiết. Khi cần dùng kết quả, xem ảnh nguồn và lấy lại ảnh rõ hơn thay vì dựa vào màu badge hay số phần trăm. Hệ thống không tự sửa một ký tự theo danh sách biển thường gặp để tăng tỷ lệ đúng giả tạo.')

page('Triển khai sao lưu và khôi phục')
p('Dự án nằm riêng trong D:\\ComputerVision\\NhanDienBienSo, gồm Git, .venv, source, models, data, runs, runtime và reports. run.cmd chuyển vào thư mục chứa nó trước khi chạy uvicorn. Môi trường đã sửa các launcher sau khi di chuyển. Trên máy mới, setup.ps1 tạo môi trường riêng, cài dependency theo lock và tải OCR kèm checksum. Sau khởi động, health cần ready và hash detector khớp báo cáo.')
code('.\\run.cmd\n# Mở http://127.0.0.1:8000\n.\\.venv\\Scripts\\python.exe scripts\\maintenance.py backup --output .local/backups/history.zip\n.\\.venv\\Scripts\\python.exe scripts\\maintenance.py verify .local/backups/history.zip')
p('Backup giữ khóa ghi SQLite trong lúc tạo snapshot và chép ảnh tham chiếu. File ZIP chứa history.sqlite3, images và manifest hash; chọn tên mới để không đè backup cũ. Snapshot không chứa model, code hoặc bí mật; code/model detector đã được lưu bằng Git, OCR có nguồn tải ghim hash. Backup cần được sao chép ra thiết bị khác để chịu lỗi ổ đĩa, thay vì chỉ có trên cùng ổ với runtime.')
p('Khôi phục bắt đầu bằng dừng API và chạy verify. Giải nén vào runtime mới trống, giữ runtime cũ, đặt PLATE_DATA_DIR tới vị trí mới rồi khởi động và đối chiếu số ảnh/bản ghi. Không ghi đè SQLite đang mở. Hợp đồng phục hồi đã được thử với 60 records/86 ảnh; không chỉ kiểm tra rằng file ZIP tồn tại.')
heading('Lưu giữ và bảo vệ dữ liệu')
code('.\\.venv\\Scripts\\python.exe scripts\\maintenance.py prune --days 30\n# Sau backup và xem dry run mới cho phép apply\n.\\.venv\\Scripts\\python.exe scripts\\maintenance.py prune --days 30 --apply')
p('Mặc định prune chỉ báo số lượt đủ tuổi, không thay dữ liệu. Khi apply, các bản ghi đã liên kết với bằng chứng bãi xe cũ được giữ; ảnh còn tham chiếu không bị xóa. Không có lịch tự động dọn. Health bổ sung storage_free_mb để giám sát; thời gian lưu phải theo nhu cầu thực tế, không tăng lưu vô hạn vì đã có chức năng chống lặp.')
p('Khi mở mạng nội bộ, bật PLATE_API_KEY và đặt reverse proxy HTTPS với giới hạn upload/request. API key hiện là quyền chung, chưa có vai trò riêng; chỉ cấp cho người được phép đọc và xóa toàn bộ lịch sử. Chạy một worker vì trạng thái voting ở RAM. Giấy phép dự án và Ultralytics cần được rà soát theo cách phân phối/triển khai cụ thể [1]; video không có khai báo quyền được giữ cục bộ để đánh giá, không đóng gói vào sản phẩm.')

page('Kế hoạch nghiệm thu tại hiện trường')
p('Nghiệm thu phải dùng camera và dữ liệu ghi mới, tách theo ngày/phiên quay và phương tiện khỏi dữ liệu đã xem. Gán nhãn tất cả lượt, gồm biển che, không thể đọc hoặc không phát hiện; giữ các lượt khó trong mẫu số. Nếu chỉ chọn những biển nguồn rõ, kết quả sẽ đánh giá điều kiện dễ hơn môi trường triển khai. Cần người thứ hai kiểm tra nhãn và khóa protocol trước khi chạy test.')
table(['Hạng mục','Phép đo cần thực hiện'],[('Ngày đêm mưa riêng','Đúng cả biển, bỏ sót, sai stable theo từng điều kiện'),('Chuyển động và lóa','Khoảng cách tốc độ độ sáng và kích thước crop'),('Sự kiện','Tỷ lệ lặp, trộn track, mất lượt và thời gian đến stable'),('Hiệu năng','p50 p95 end to end, khung trễ và tải nhiều biển'),('Độ bền','Chạy liên tục nhiều giờ, lỗi mạng camera và restart'),('Phục hồi','Khôi phục snapshot trên máy/ổ khác, đối chiếu đủ ảnh')],[5.3,10.9])
p('Ngưỡng nghiệm thu phải được chủ triển khai chốt trước, theo mức độ hậu quả khi đọc sai và lượng người đối chiếu. Đồ án chưa có dữ liệu hiện trường để cam kết một SLA hoặc độ chính xác 99%. Bản hiện tại cho phép thử vận hành trên một máy với người quan sát; chưa coi là nghiệm thu tự động không người kiểm tra.')
heading('Các ưu tiên tiếp theo')
p('Ưu tiên đầu tiên là tập độc lập cho camera dự định dùng, nhất là đêm, lóa và mưa. Tiếp theo là cải thiện OCR bằng dữ liệu chuỗi Việt Nam được gán nhãn đúng và tách train/validation/test theo xe/phiên, thay vì chỉ train thêm detector. Khi có nhiều trường hợp nghiêng, cần đánh giá nắn phối cảnh bằng keypoint; khi thực sự có nhiều camera, cần trạng thái chia sẻ và hàng đợi có backpressure cùng phép đo tải.')
p('Mỗi cải tiến cần baseline và tiêu chí hồi quy để không làm xấu ảnh gốc. Không thêm model khử mờ chỉ vì tên công nghệ: nếu tạo chi tiết không có trong ảnh, kết quả có thể trông nét nhưng đọc sai ký tự. Không bỏ quality/review để đổi lấy số sự kiện nhiều hơn. Phân quyền, ghi log truy cập và tự giám sát restart chỉ nên triển khai khi yêu cầu vận hành nhiều người/camera đã xác định rõ.')

page('Chương 7 Kết luận',1)
p('Đồ án đã hoàn thành chuỗi sản phẩm từ dữ liệu đến ứng dụng: chuẩn bị nhãn và split, huấn luyện detector, tích hợp OCR, API ảnh, giao diện ảnh/camera/video, tra cứu và CSV. Phiên bản 1.3.0 bổ sung gán track dự đoán chuyển động, voting bảo thủ, chống lưu lặp, ROI, lý do review và công cụ backup/verify/prune. Dữ liệu lịch sử được giữ sau khi chuyển thư mục, thay đổi giao diện và migration schema.')
p('Kết quả detector trên test gốc đạt mAP@50 99,11% và mAP@50–95 87,50%. Fine-tune cải thiện detector dưới mờ mô phỏng, nhưng không làm tăng mọi chỉ số. OCR vẫn là giới hạn lớn khi chữ mất chi tiết: chỉ 3/37 mẫu mờ ngang mạnh đọc đúng cả biển. Việc giữ cảnh báo và chọn khung rõ có cơ sở từ chính kết quả thực nghiệm này.')
p('Video thật bổ sung mức kiểm chứng thực dụng: năm mục tiêu ban ngày và một biển xe máy trong nhà được đọc stable; cảnh đêm đạt hai trong ba mục tiêu chọn stable. Một số chuỗi đúng một khung vẫn bị giữ review do thiếu chứng cứ thời gian. Điều này thể hiện lựa chọn giảm chấp nhận vội; không chứng minh không còn lỗi OCR hoặc lỗi ghép. Các video đã dùng phát triển cần được thay bằng bộ độc lập để nghiệm thu.')
p('Chín kiểm thử Python, các bộ điều khiển camera/video và thử API/model thật đã đạt trong phạm vi đã mô tả. Snapshot 60 records/86 ảnh đã verify và khôi phục thử với integrity_check ok. Giao diện video gộp 18 khung thành một lượt stable khi không lưu; dữ liệu người dùng không bị thêm ngầm. Mã nguồn, detector và báo cáo được lưu trong GitHub; dữ liệu vận hành và video nguồn giữ cục bộ.')
p('Sản phẩm có thể dùng để thử triển khai nhận diện và tra cứu với người đối chiếu trên một máy. Chưa tuyên bố hoàn thiện cho tất cả bối cảnh đêm/mưa/chuyển động hoặc chạy 24/7 không giám sát. Công việc còn lại trước nghiệm thu là dữ liệu camera mới, nhãn đầy đủ và đo định lượng chất lượng, độ trễ cùng phục hồi dài hạn. Phạm vi bãi giữ xe đã được tạm bỏ; báo cáo tập trung vào bài toán nhận diện biển số theo sản phẩm hiện tại.')

page('Tài liệu tham khảo',1)
references=[
 '[1] Glenn Jocher và Jing Qiu. Ultralytics YOLO11. Tài liệu và cấu hình mô hình chính thức. https://docs.ultralytics.com/models/yolo11/ và https://github.com/ultralytics/ultralytics. Truy cập ngày 6 tháng 10 năm 2026.',
 '[2] Ali Hassani và cộng sự. Escaping the Big Data Paradigm with Compact Transformers. arXiv 2104.05704. https://arxiv.org/abs/2104.05704. Nguồn lý thuyết Compact Convolutional Transformer.',
 '[3] FastPlateOCR. Tài liệu và pretrained CCT S v2 global OCR. https://ankandrew.github.io/fast-plate-ocr/latest/ và https://github.com/ankandrew/fast-plate-ocr. URL file và hash riêng trong models/ocr_provenance.json.',
 '[4] Huy Che Quang và cộng sự. Character Time-series Matching For Robust License Plate Recognition. MAPR 2022. https://arxiv.org/abs/2307.11336 và https://github.com/chequanghuy/Character-Time-series-Matching. Tham khảo nghiên cứu nhận diện qua thời gian; thuật toán đồ án được hiện thực riêng.',
 '[5] hoanglvuit. Vietnam License Plate Segment Datasets. Hugging Face. https://huggingface.co/datasets/hoanglvuit/Vietnam_License_Plate_Segment_Datasets/tree/b8a1e809cadea0e53b1c519f637d494f0d87796f. Revision và SHA-256 được giữ trong manifest của dự án.',
 '[6] longphungtuan94. ALPR_System. Video test_videos/test.MOV, revision 0a6d781137870ac362262bb1fa9b0fdf4d99e49d. https://github.com/longphungtuan94/ALPR_System. Repository khai báo Apache-2.0; clip chỉ dùng đánh giá và không phát hành lại.',
 '[7] ddkhoa2605. LicensePlateDetection. Video_Test/video1.mp4 và cam_20250922_181322.mp4, revision f1c732e2270becc44df1de6529372f63ef251076. https://github.com/ddkhoa2605/LicensePlateDetection. Chưa thấy khai báo giấy phép; giữ video cục bộ để đánh giá, không đóng gói trong repo sản phẩm.',
 '[8] FastAPI. Request Forms and Files, TestClient và deployment. https://fastapi.tiangolo.com/tutorial/request-forms-and-files/ và https://fastapi.tiangolo.com/deployment/. Tài liệu API thư viện được dùng hiện thực.',
 '[9] Python Software Foundation. sqlite3 Online backup và transaction control. https://docs.python.org/3.12/library/sqlite3.html. Cơ sở triển khai snapshot database.',
 '[10] Dự án NhanDienBienSo. Báo cáo thực nghiệm JSON và mã nguồn phiên bản 1.3.0, ngày 6 tháng 10 năm 2026. training.json, hardening.json, ocr_weather.json, real_video.json, operation_validation.json và RELEASE_VALIDATION.md.'
]
for reference in references:
    paragraph=p(reference);paragraph.paragraph_format.line_spacing=1.05;paragraph.paragraph_format.space_after=Pt(9)
    paragraph.alignment=WD_ALIGN_PARAGRAPH.LEFT
    for run in paragraph.runs:run.font.size=Pt(11.5)

page('Phụ lục Tái lập và giao thức API',1)
heading('Tổ chức file và thực thi')
code('NhanDienBienSo/\n  app.py  recognition.py  temporal.py\n  models/    reports/    scripts/    tests/    web/\n  data/      runs/       runtime/    .venv/\n  run.cmd    setup.ps1   requirements-lock.txt')
code('.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v\nnode tests/check_camera_js.cjs\nnode tests/check_video_js.cjs\n.\\.venv\\Scripts\\python.exe scripts/evaluate_video.py --device auto')
p('evaluate_video.py tải clip nguồn nếu file thiếu, chặn quá 100 MB và kiểm tra hash ghim trong manifest. Các trọng số và threshold không tự thay sau phép đo. build_report.py tạo DOCX từ các JSON thực nghiệm; cần dependency authoring python-docx và Pillow. Các lệnh vận hành sản phẩm dùng môi trường riêng của dự án. Bộ dựng báo cáo trong lần bàn giao dùng runtime tài liệu đã cài.')
heading('Ví dụ phiên API và định nghĩa phản hồi')
code('POST /api/recognize  multipart/form-data\nfile = frame.jpg\nsource = video:sample.mp4:0.40s\nconfidence = 0.35\nsave = false\nstream_id = UUID mới của phiên\nsample_time = 0.40')
p('detections trả chuỗi raw/display, bbox, layout, điểm detector/OCR, quality, needs_review, saved và temporal. temporal gồm track_id, status pending/review/stable, chuỗi consensus khi đủ điều kiện, số votes/observations và new_event. Chỉ saved=true mới có image_url/crop_url dùng tra cứu. new_event là điều kiện có thể lưu, không chứng minh bản ghi đã được lưu. Khi save=false, voting vẫn chạy nhưng không thêm lịch sử.')
heading('Nhận diện phiên bản trọng số')
code('Detector SHA-256\n'+training['weights_sha256'])
p('Hash này cần trùng health API và các báo cáo model đang dùng. Kết quả qua phiên bản khác phải được đo lại theo cùng protocol. Các JSON giữ số liệu chi tiết từng frame, nguồn clip, cấu hình và giới hạn; báo cáo không thay thế dữ liệu gốc để kiểm tra lại kết luận.')

document.save(OUT)
print(str(OUT))
print('Authored paragraphs:',len(document.paragraphs),'tables:',len(document.tables))
