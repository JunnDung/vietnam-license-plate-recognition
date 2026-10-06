'use strict';
const $ = id => document.getElementById(id);
let selectedFile, stream, cameraTimer, cameraGeneration = 0, busy = false, historyOffset = 0, imageUrls = [];
let noticeTimer;
const key = () => sessionStorage.getItem('plate-api-key') || '';
$('api-key').value = key();
function notice(message, error = false) {
  clearTimeout(noticeTimer); $('notice').textContent = message; $('notice').className = error ? 'error' : '';
  $('notice').hidden = false; noticeTimer = setTimeout(() => $('notice').hidden = true, 7000);
}
async function api(url, options = {}) {
  const response = await fetch(url, {...options, headers: {...options.headers, 'X-API-Key': key()}});
  if (!response.ok) {
    let message = `Yêu cầu thất bại (${response.status})`;
    try { const body = await response.json(); message = typeof body.detail === 'string' ? body.detail : message; } catch {}
    throw new Error(message);
  }
  return response;
}
function element(tag, className, text) {
  const node = document.createElement(tag); node.className = className || ''; if (text !== undefined) node.textContent = text; return node;
}
function releaseImages() { imageUrls.forEach(URL.revokeObjectURL); imageUrls = []; }
async function imageUrl(url) { const blob = await (await api(url)).blob(); const result = URL.createObjectURL(blob); imageUrls.push(result); return result; }
function busyState(value) {
  busy = value; $('recognize-btn').disabled = value || !selectedFile || !!stream || videoRunning;
  $('camera-start').disabled = value || !!stream || videoRunning; $('video-start').disabled = value || videoRunning || !videoURL || !!stream;
  $('latency').textContent = value ? 'ĐANG XỬ LÝ…' : 'SẴN SÀNG';
}
function draw(image, detections = []) {
  const canvas = $('preview-canvas'); canvas.width = image.videoWidth || image.naturalWidth || image.width; canvas.height = image.videoHeight || image.naturalHeight || image.height;
  const context = canvas.getContext('2d'); context.drawImage(image, 0, 0, canvas.width, canvas.height);
  context.lineWidth = Math.max(2, canvas.width / 350); context.font = `${Math.max(15, canvas.width / 45)}px sans-serif`;
  for (const detection of detections) {
    const [x0,y0,x1,y1] = detection.bbox; context.strokeStyle = detection.needs_review ? '#ffb69d' : '#b5f369'; context.fillStyle = context.strokeStyle;
    context.strokeRect(x0, y0, x1-x0, y1-y0); context.fillText(detection.display_plate || 'Chưa đọc được', x0, Math.max(22,y0-7));
  }
  canvas.hidden = false; $('preview-empty').hidden = true; $('camera-video').hidden = !stream;
  $('frame-caption').hidden = !stream && !videoURL;
}
async function loadFile(file) {
  if (!file) return;
  if (busy) {notice('Chờ lượt đang xử lý xong trước khi đổi ảnh.');return;}
  if (file.size > 10*1024*1024 || !['image/jpeg','image/png','image/webp'].includes(file.type)) { notice('Chọn JPG, PNG hoặc WebP, dung lượng tối đa 10 MB.', true); return; }
  stopCamera();
  clearVideo();
  const generation = cameraGeneration;
  const url = URL.createObjectURL(file), image = new Image();
  try { await new Promise((resolve,reject) => { image.onload = resolve; image.onerror = reject; image.src = url; });
    if (generation !== cameraGeneration) return;
    if (image.naturalWidth * image.naturalHeight > 16000000) throw new Error('Ảnh vượt quá 16 triệu pixel.');
    draw(image); selectedFile = file; $('filename').textContent = `${file.name} · ${(file.size/1024).toFixed(0)} KB`;
    $('results').replaceChildren(element('p','hint','Đã chọn ảnh. Bấm Nhận diện ảnh để xử lý.')); $('recognize-btn').disabled = busy;
  } catch (error) { notice(error.message || 'Không đọc được ảnh.', true); } finally { URL.revokeObjectURL(url); }
}
function renderResults(data) {
  $('results').replaceChildren();
  for (const item of data.detections) {
    const row = element('div','result-row'), info = element('div');
    info.append(element('div','result-plate',item.display_plate || 'Chưa đọc được'),element('div','result-meta',`Phát hiện ${(item.detector_confidence*100).toFixed(1)}% · OCR ${(item.ocr_confidence*100).toFixed(1)}% · ${item.layout === 'two_lines' ? 'Biển hai dòng' : 'Biển một dòng'}`));
    const qualityLabels={low_light:'Vùng biển thiếu sáng',low_detail:'Vùng biển ít chi tiết hoặc mờ',small_plate:'Biển quá nhỏ trong ảnh'};
    if(item.quality?.issues?.length) info.append(element('p','hint',item.quality.issues.map(issue=>qualityLabels[issue] || issue).join(' · ')+'. Lấy ảnh rõ hơn và đối chiếu ký tự.'));
    if(item.ocr_disagreement) info.append(element('p','hint','Các biến thể ảnh trả ký tự khác nhau. Đối chiếu biển số dù điểm OCR cao.'));
    row.append(info,element('span',`badge${item.needs_review ? ' review' : ''}`,item.needs_review ? 'Cần kiểm tra' : 'Đã đọc'));
    $('results').append(row);
  }
  if (!data.detections.length) $('results').append(element('p','hint','Không phát hiện biển số. Thử ảnh rõ hơn hoặc giảm ngưỡng phát hiện.'));
  $('latency').textContent = `${data.latency_ms.toFixed(0)} MS · ${data.detections.length} BIỂN SỐ`;
}
async function processFile(file, source, image, active = ()=>true, save = $('save-history').checked) {
  if (busy || !active()) return null;
  busyState(true);
  try {
    const form = new FormData(); form.append('file',file,'frame.jpg'); form.append('source',source); form.append('confidence',$('threshold').value); form.append('save',save);
    const data = await (await api('/api/recognize',{method:'POST',body:form})).json();
    if (!active()) return null;
    draw(image,data.detections); busyState(false); renderResults(data);
    return data;
  } catch (error) { if (active()) {notice(error.message,true);if (source === 'camera') stopCamera();}return null; }
  finally {if(busy) busyState(false);}
}
$('image-file').addEventListener('change', event => loadFile(event.target.files[0]));
$('drop-zone').addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); $('image-file').click(); } });
for (const event of ['dragenter','dragover']) $('drop-zone').addEventListener(event,e => { e.preventDefault(); $('drop-zone').classList.add('drag'); });
for (const event of ['dragleave','drop']) $('drop-zone').addEventListener(event,e => { e.preventDefault(); $('drop-zone').classList.remove('drag'); });
$('drop-zone').addEventListener('drop', event => loadFile(event.dataTransfer.files[0]));
$('threshold').addEventListener('input',()=> $('threshold-value').textContent = Number($('threshold').value).toFixed(2));
$('recognize-btn').addEventListener('click',async()=> { if (!selectedFile || busy) return; const image = await createImageBitmap(selectedFile); try { await processFile(selectedFile,'upload',image); } finally { image.close(); } });
function stopCamera() {
  cameraGeneration++; clearTimeout(cameraTimer); if (stream) stream.getTracks().forEach(track=>track.stop()); stream = null;
  $('camera-video').srcObject = null; $('camera-video').hidden = true; $('camera-stop').disabled = true; busyState(busy);
}
$('camera-stop').addEventListener('click',stopCamera);
$('camera-start').addEventListener('click',async()=> {
  if (busy) { notice('Chờ xử lý ảnh xong trước khi bật camera.'); return; }
  clearVideo();
  const generation = ++cameraGeneration; $('camera-start').disabled = true;
  try {
    const acquired = await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1280},height:{ideal:720},frameRate:{ideal:30,max:60},facingMode:'environment'},audio:false});
    if (generation !== cameraGeneration) { acquired.getTracks().forEach(track=>track.stop()); return; }
    stream = acquired; $('camera-video').srcObject = stream; await $('camera-video').play(); $('camera-video').hidden = false; $('preview-empty').hidden = true; $('camera-stop').disabled = false; busyState(false);
    $('filename').textContent = 'Camera trực tiếp · khung nhận diện hiển thị phía dưới';
    $('frame-caption').textContent = 'Khung đã phân tích · hình xem trực tiếp phía trên chạy độc lập.';
    const previewFPS = stream.getVideoTracks()[0].getSettings().frameRate, completed = [];
    async function capture() {
      if (!stream || generation !== cameraGeneration) return;
      const start = performance.now(), active = ()=>stream && generation===cameraGeneration;
      const frame = await captureBestFrame($('camera-video'),()=>stream && generation===cameraGeneration);
      if (!frame) return;
      const blob = await new Promise(resolve=>frame.toBlob(resolve,'image/jpeg',.9));
      if (!blob) throw new Error('Không lấy được ảnh từ camera.');
      if (!stream || generation !== cameraGeneration) return;
      const data = await processFile(blob,'camera',frame,active);
      if (!active()) return;
      if (!data) {stopCamera();return;}
      completed.push(performance.now()); if(completed.length>10) completed.shift();
      const rate = completed.length>1 ? 1000*(completed.length-1)/(completed.at(-1)-completed[0]) : null;
      $('camera-rate').textContent = `Xem trực tiếp: ${previewFPS ? previewFPS.toFixed(0)+' FPS' : 'theo camera'} · mục tiêu ${$('camera-fps').value} lượt/giây · thực đạt ${rate===null ? 'đang đo' : rate.toFixed(1)+' lượt/giây'}`;
      cameraTimer = setTimeout(()=>capture().catch(error=>{stopCamera();notice(error.message,true);}),frameDelay(start,Number($('camera-fps').value)));
    }
    await capture();
  } catch { stopCamera(); notice('Không mở được camera. Kiểm tra quyền truy cập, camera đang được sử dụng và kết nối localhost/HTTPS.',true); }
});
function searchParams() {
  const params = new URLSearchParams({plate:$('search-plate').value});
  for (const [field,name] of [['search-from','since'],['search-to','until']]) if ($(field).value) params.set(name,new Date($(field).value+'+07:00').toISOString());
  return params;
}
async function showHistory() {
  const params = searchParams(); params.set('offset',historyOffset); params.set('limit',30);
  try {
    const data = await (await api('/api/history?'+params)).json(); releaseImages(); $('history-body').replaceChildren();
    if (historyOffset > 0 && !data.items.length && data.total > 0) {historyOffset=0;return showHistory();}
    $('history-empty').hidden = data.items.length > 0; $('history-count').textContent = data.total ? `${historyOffset+1}–${historyOffset+data.items.length} / ${data.total} kết quả` : '0 kết quả';
    $('prev-btn').disabled = historyOffset === 0; $('next-btn').disabled = historyOffset+30 >= data.total;
    for (const item of data.items) {
      const row = element('tr');
      row.append(element('td','',item.display_plate || 'Chưa đọc được')); const cropCell = element('td');
      const crop = element('img'); crop.alt = `Ảnh biển số ${item.display_plate}`; cropCell.append(crop); row.append(cropCell);
      imageUrl(item.crop_url).then(url=>crop.src=url).catch(()=>crop.alt='Ảnh không khả dụng');
      row.append(element('td','',new Date(item.created_at).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'})),element('td','',item.source),element('td','',`${(item.ocr_confidence*100).toFixed(1)}%`));
      const stateCell = element('td'); stateCell.append(element('span',`badge${item.needs_review ? ' review' : ''}`,item.needs_review ? 'Cần kiểm tra' : 'Đã đọc')); row.append(stateCell);
      const action = element('td'), view = element('button','','Xem ảnh'), remove = element('button','','Xóa');
      view.addEventListener('click',async()=> { try { $('dialog-image').src=await imageUrl(item.image_url); $('image-dialog').showModal(); } catch(error) { notice(error.message,true); } });
      remove.addEventListener('click',async()=> { if (!confirm('Xóa lượt nhận diện và ảnh lưu của lượt này?')) return; try { await api('/api/history/'+item.id,{method:'DELETE'}); await showHistory(); } catch(error) { notice(error.message,true); } });
      action.append(view,document.createTextNode(' '),remove); row.append(action); $('history-body').append(row);
    }
  } catch(error) { notice(error.message,true); }
}
$('search-form').addEventListener('submit',event=> { event.preventDefault(); historyOffset=0; showHistory(); });
$('prev-btn').addEventListener('click',()=> { historyOffset=Math.max(0,historyOffset-30); showHistory(); });
$('next-btn').addEventListener('click',()=> { historyOffset+=30; showHistory(); });
$('export-btn').addEventListener('click',async()=> { try { const blob=await (await api('/api/history.csv?'+searchParams())).blob(), url=URL.createObjectURL(blob), anchor=element('a'); anchor.href=url; anchor.download='plate-history.csv'; anchor.click(); setTimeout(()=>URL.revokeObjectURL(url),1000); } catch(error) { notice(error.message,true); } });
$('dialog-close').addEventListener('click',()=> $('image-dialog').close());
async function showModel() {
  try {
    const data=await (await api('/api/model')).json(); $('metrics').replaceChildren(); const test=data.training?.test || {};
    const metrics=[['mAP@50 · detection / test',test['metrics/mAP50(B)']],['mAP@50–95 · detection / test',test['metrics/mAP50-95(B)']],['Recall · detection / test',test['metrics/recall(B)']]];
    if (data.ocr_evaluation) metrics.push(['Đọc đúng cả biển · crop có nhãn',data.ocr_evaluation.exact_match], ['Phát hiện + đọc đúng · mẫu OCR',data.ocr_evaluation.pipeline_exact_match]);
    for(const [label,value] of metrics) { const card=element('div','metric'); card.append(element('b','',value===undefined ? 'Chưa đo' : `${(value*100).toFixed(1)}%`),element('span','',label)); $('metrics').append(card); }
    if(data.ocr_evaluation) $('metrics').append(element('p','hint',`Mẫu OCR: ${data.ocr_evaluation.samples} biển số được phiên âm bằng mắt từ ảnh test. Mẫu nhỏ, không đại diện toàn bộ camera.`));
    const conditions={original:'Ảnh gốc',synthetic_dark:'Thiếu sáng mô phỏng',synthetic_rain_fog:'Mưa/sương mô phỏng',synthetic_motion_blur:'Mờ chuyển động mô phỏng'};
    if(data.robustness) for(const [name,item] of Object.entries(data.robustness.conditions)) {
      const card=element('div','metric'), before=data.hardening?.baseline?.test?.robustness?.conditions?.[name];
      card.append(element('b','',`${(item.recall_at_iou50*100).toFixed(1)}%`),element('span','',`Recall detector @ IoU50 · ${conditions[name] || name} (${item.images} ảnh)`));
      if(before) card.append(element('span','',`Trước cập nhật: ${(before.recall_at_iou50*100).toFixed(1)}% · cùng ảnh và ngưỡng`));
      $('metrics').append(card);
    }
    if(data.ocr_weather) for(const [name,item] of Object.entries(data.ocr_weather.conditions)) {
      const card=element('div','metric'); card.append(element('b',item.pipeline_exact_match<.8 ? 'low-metric' : '',`${(item.pipeline_exact_match*100).toFixed(1)}%`),element('span','',`Phát hiện + đọc đúng cả biển · ${conditions[name] || name} (${item.samples} mẫu)`)); $('metrics').append(card);
      const before=data.hardening?.baseline?.test?.ocr_weather?.conditions?.[name];
      if(before) card.append(element('span','',`Trước cập nhật: ${(before.pipeline_exact_match*100).toFixed(1)}% · cùng mẫu OCR`));
    }
    if(data.ocr_weather) $('metrics').append(element('p','hint','OCR điều kiện khó: dùng cùng mẫu đọc được ở ảnh gốc, không loại thêm mẫu sau khi làm mờ/thiếu sáng. Chưa kiểm chứng camera thực.'));
  } catch(error) { notice(error.message,true); }
}
document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=> {
  if(button.dataset.tab!=='recognize') {stopCamera();stopVideo();}
  document.querySelectorAll('[data-tab]').forEach(tab=> {const active=tab===button;tab.classList.toggle('active',active);tab.setAttribute('aria-selected',active);});
  document.querySelectorAll('.panel').forEach(panel=>panel.hidden=panel.id!==button.dataset.tab);
  if(button.dataset.tab==='history') showHistory(); if(button.dataset.tab==='model') showModel();
}));
$('key-save').addEventListener('click',()=> { sessionStorage.setItem('plate-api-key',$('api-key').value); notice('Đã áp dụng API key cho phiên trình duyệt này.'); });
async function checkHealth() { try { const data=await (await api('/api/health')).json(); $('status').textContent=data.status==='ready' ? 'Mô hình sẵn sàng' : 'Chưa tải được mô hình'; $('status').classList.toggle('ready',data.status==='ready'); } catch { $('status').textContent='Mất kết nối API'; $('status').classList.remove('ready'); } }
checkHealth(); setInterval(checkHealth,30000);
window.addEventListener('pagehide',()=> {stopCamera();clearVideo();releaseImages();});
