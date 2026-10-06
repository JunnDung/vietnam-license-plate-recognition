'use strict';
const $ = id => document.getElementById(id);
let selectedFile, stream, cameraTimer, cameraGeneration = 0, busy = false, historyOffset = 0, imageUrls = [];
let noticeTimer;
let parkingOffset = 0, parkingCandidate = null, parkingDirection = 'in';
let parkingCurrentReady = false, parkingEntryReady = false;
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
function busyState(value) { busy = value; $('recognize-btn').disabled = value || !selectedFile || !!stream; $('latency').textContent = value ? 'ĐANG XỬ LÝ…' : 'SẴN SÀNG'; document.querySelectorAll('.gate-actions button').forEach(button=>button.disabled=value); }
function draw(image, detections = []) {
  const canvas = $('preview-canvas'); canvas.width = image.videoWidth || image.naturalWidth || image.width; canvas.height = image.videoHeight || image.naturalHeight || image.height;
  const context = canvas.getContext('2d'); context.drawImage(image, 0, 0, canvas.width, canvas.height);
  context.lineWidth = Math.max(2, canvas.width / 350); context.font = `${Math.max(15, canvas.width / 45)}px sans-serif`;
  for (const detection of detections) {
    const [x0,y0,x1,y1] = detection.bbox; context.strokeStyle = detection.needs_review ? '#ffb69d' : '#b5f369'; context.fillStyle = context.strokeStyle;
    context.strokeRect(x0, y0, x1-x0, y1-y0); context.fillText(detection.display_plate || 'Chưa đọc được', x0, Math.max(22,y0-7));
  }
  canvas.hidden = false; $('preview-empty').hidden = true; $('camera-video').hidden = true;
}
async function loadFile(file) {
  if (!file) return;
  if (file.size > 10*1024*1024 || !['image/jpeg','image/png','image/webp'].includes(file.type)) { notice('Chọn JPG, PNG hoặc WebP, dung lượng tối đa 10 MB.', true); return; }
  stopCamera();
  const url = URL.createObjectURL(file), image = new Image();
  try { await new Promise((resolve,reject) => { image.onload = resolve; image.onerror = reject; image.src = url; });
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
    row.append(info,element('span',`badge${item.needs_review ? ' review' : ''}`,item.needs_review ? 'Cần kiểm tra' : 'Đã đọc'));
    const actions=element('div','gate-actions');
    if(item.image_url) for(const [direction,label] of [['in','Xe vào →'],['out','Xe ra →']]) { const button=element('button','',label);button.addEventListener('click',()=>openParkingConfirm(item,direction));actions.append(button); }
    else actions.append(element('span','hint','Bật lưu lịch sử và nhận diện lại để xác nhận xe vào/ra.'));
    row.append(actions); $('results').append(row);
  }
  if (!data.detections.length) $('results').append(element('p','hint','Không phát hiện biển số. Thử ảnh rõ hơn hoặc giảm ngưỡng phát hiện.'));
  $('latency').textContent = `${data.latency_ms.toFixed(0)} MS · ${data.detections.length} BIỂN SỐ`;
}
async function processFile(file, source, image) {
  if (busy) return;
  busyState(true);
  try {
    const form = new FormData(); form.append('file',file,'frame.jpg'); form.append('source',source); form.append('confidence',$('threshold').value); form.append('save',$('save-history').checked);
    const data = await (await api('/api/recognize',{method:'POST',body:form})).json();
    draw(image,data.detections); busyState(false); renderResults(data);
  } catch (error) { busyState(false); notice(error.message,true); if (source === 'camera') stopCamera(); }
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
  $('camera-video').srcObject = null; $('camera-stop').disabled = true; $('camera-start').disabled = false; $('recognize-btn').disabled = busy || !selectedFile;
}
$('camera-stop').addEventListener('click',stopCamera);
$('camera-start').addEventListener('click',async()=> {
  if (busy) { notice('Chờ xử lý ảnh xong trước khi bật camera.'); return; }
  const generation = ++cameraGeneration; $('camera-start').disabled = true;
  try {
    const acquired = await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1280},height:{ideal:720},facingMode:'environment'},audio:false});
    if (generation !== cameraGeneration) { acquired.getTracks().forEach(track=>track.stop()); return; }
    stream = acquired; $('camera-video').srcObject = stream; await $('camera-video').play(); $('camera-stop').disabled = false; $('recognize-btn').disabled = true;
    $('filename').textContent = 'Camera trực tiếp · mỗi 3 giây sau khi xử lý';
    async function capture() {
      if (!stream || generation !== cameraGeneration) return;
      const video = $('camera-video'), frame = document.createElement('canvas'); frame.width = video.videoWidth; frame.height = video.videoHeight;
      frame.getContext('2d').drawImage(video,0,0); const blob = await new Promise(resolve=>frame.toBlob(resolve,'image/jpeg',.9));
      if (!stream || generation !== cameraGeneration) return;
      await processFile(blob,'camera',frame);
      if (stream && generation === cameraGeneration) cameraTimer = setTimeout(capture,3000);
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
    if(data.robustness) for(const [name,item] of Object.entries(data.robustness.conditions)) { const card=element('div','metric'); card.append(element('b','',`${(item.recall_at_iou50*100).toFixed(1)}%`),element('span','',`Recall @ IoU50 · ${conditions[name] || name} (${item.images} ảnh)`)); $('metrics').append(card); }
  } catch(error) { notice(error.message,true); }
}
function vnTime(value) {return value ? new Date(value).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}) : '—';}
function durationText(seconds) {const minutes=Math.floor(seconds/60);return `${Math.floor(minutes/60)} giờ ${minutes%60} phút`;}
async function showParking() {
  try {
    const params=new URLSearchParams({plate:$('parking-search-plate').value,status:$('parking-status').value,limit:30,offset:parkingOffset});
    const data=await (await api('/api/parking?'+params)).json();
    if(parkingOffset>0 && !data.items.length && data.total>0) {parkingOffset=0;return showParking();}
    releaseImages();$('parking-body').replaceChildren();$('inside-count').textContent=data.inside;$('entered-count').textContent=data.entered_today;$('exited-count').textContent=data.exited_today;
    $('parking-empty').hidden=!!data.items.length;$('parking-count').textContent=`${data.total} lượt gửi`;$('parking-prev').disabled=parkingOffset===0;$('parking-next').disabled=parkingOffset+30>=data.total;
    for(const item of data.items) {
      const row=element('tr');row.append(element('td','',item.display_plate));const images=element('td');
      for(const [url,title] of [[item.entry_crop_url,'Biển số lúc vào'],[item.exit_crop_url,'Biển số lúc ra']]) if(url) {const picture=element('img');picture.alt=title;images.append(picture);imageUrl(url).then(value=>picture.src=value).catch(()=>picture.alt='Ảnh không khả dụng');}
      row.append(images,element('td','',vnTime(item.entered_at)),element('td','',vnTime(item.exited_at)),element('td','',durationText(item.duration_seconds)));
      const state=element('td');state.append(element('span','badge',item.status==='active' ? 'Đang trong bãi' : 'Đã ra'));row.append(state);
      const action=element('td');for(const [url,label] of [[item.entry_image_url,'Ảnh vào'],[item.exit_image_url,'Ảnh ra']]) if(url) {const button=element('button','',label);button.addEventListener('click',async()=>{try{$('dialog-image').src=await imageUrl(url);$('image-dialog').showModal();}catch(error){notice(error.message,true);}});action.append(button,document.createTextNode(' '));}
      if(item.entry_corrected || item.exit_corrected) action.append(element('p','hint','Có sửa OCR sau đối chiếu'));
      row.append(action);$('parking-body').append(row);
    }
  } catch(error) {notice(error.message,true);}
}
function updateParkingSubmit() {$('parking-submit').disabled=!$('parking-ack').checked || !parkingCurrentReady || (parkingDirection==='out' && !parkingEntryReady);}
async function lookupParkingEntry() {
  $('parking-ack').checked=false;$('parking-submit').disabled=true;$('parking-entry-proof').hidden=true;
  parkingEntryReady=false;
  if(parkingDirection==='in') {$('parking-confirm-info').textContent='Sẽ tạo lượt gửi mới khi bạn xác nhận.';return;}
  const plate=$('parking-plate').value;
  $('parking-confirm-info').textContent='Đang tìm lượt vào để đối chiếu…';
  try {
    const data=await (await api('/api/parking?'+new URLSearchParams({plate,status:'active',limit:100}))).json();
    if(plate!==$('parking-plate').value || !$('parking-dialog').open) return;
    const normalized=plate.toUpperCase().replace(/[^A-Z0-9]/g,''), session=data.items.find(item=>item.plate===normalized);
    if(!session) {$('parking-confirm-info').textContent='Chưa tìm thấy lượt vào khớp. Kiểm tra hoặc sửa biển số trước khi xác nhận.';return;}
    const entryUrl=await imageUrl(session.entry_image_url);
    if(plate!==$('parking-plate').value || !$('parking-dialog').open) return;
    $('parking-entry-image').src=entryUrl;$('parking-entry-text').textContent=`${session.display_plate} · Vào ${vnTime(session.entered_at)} · ${durationText(session.duration_seconds)}`;
    $('parking-entry-proof').hidden=false;$('parking-confirm-info').textContent='Đối chiếu phương tiện và biển số giữa ảnh vào và ảnh hiện tại.';
    parkingEntryReady=true;updateParkingSubmit();
  }catch(error){$('parking-confirm-info').textContent=error.message;}
}
async function openParkingConfirm(item,direction) {
  stopCamera();parkingCandidate=item;parkingDirection=direction;$('parking-confirm-title').textContent=direction==='in' ? 'Xác nhận xe vào' : 'Đối chiếu xe ra';
  parkingCurrentReady=false;parkingEntryReady=false;
  $('parking-submit').textContent=direction==='in' ? 'Ghi nhận xe vào' : 'Ghi nhận xe ra';$('parking-plate').value=item.display_plate || item.plate;
  $('parking-current-image').removeAttribute('src');$('parking-current-crop').removeAttribute('src');$('parking-dialog').showModal();await lookupParkingEntry();
  try {const current=await imageUrl(item.image_url),crop=await imageUrl(item.crop_url);if(parkingCandidate?.id!==item.id || !$('parking-dialog').open) return;$('parking-current-image').src=current;$('parking-current-crop').src=crop;parkingCurrentReady=true;updateParkingSubmit();}catch(error){notice(error.message,true);}
}
$('parking-search-form').addEventListener('submit',event=>{event.preventDefault();parkingOffset=0;showParking();});
$('parking-refresh').addEventListener('click',showParking);
$('parking-prev').addEventListener('click',()=>{parkingOffset=Math.max(0,parkingOffset-30);showParking();});
$('parking-next').addEventListener('click',()=>{parkingOffset+=30;showParking();});
$('parking-cancel').addEventListener('click',()=> $('parking-dialog').close());
$('parking-plate').addEventListener('input',()=>{$('parking-ack').checked=false;parkingEntryReady=false;updateParkingSubmit();$('parking-entry-proof').hidden=true;});
$('parking-plate').addEventListener('change',lookupParkingEntry);
$('parking-ack').addEventListener('change',updateParkingSubmit);
$('parking-confirm-form').addEventListener('submit',async event=>{
  event.preventDefault();if(!parkingCandidate || !$('parking-ack').checked) return;$('parking-submit').disabled=true;
  try {const data=await (await api('/api/parking/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({record_id:parkingCandidate.id,plate:$('parking-plate').value,direction:parkingDirection,confirmed:true})})).json();
    $('parking-dialog').close();notice(`${data.direction==='in' ? 'Đã ghi nhận xe vào' : 'Đã ghi nhận xe ra'}: ${data.session.display_plate}`);
    document.querySelector('[data-tab="parking"]').click();
  }catch(error){notice(error.message,true);$('parking-submit').disabled=false;}
});
document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=> {
  if(button.dataset.tab!=='recognize') stopCamera();
  document.querySelectorAll('[data-tab]').forEach(tab=> {const active=tab===button;tab.classList.toggle('active',active);tab.setAttribute('aria-selected',active);});
  document.querySelectorAll('.panel').forEach(panel=>panel.hidden=panel.id!==button.dataset.tab);
  if(button.dataset.tab==='history') showHistory(); if(button.dataset.tab==='model') showModel();if(button.dataset.tab==='parking') showParking();
}));
$('key-save').addEventListener('click',()=> { sessionStorage.setItem('plate-api-key',$('api-key').value); notice('Đã áp dụng API key cho phiên trình duyệt này.'); });
async function checkHealth() { try { const data=await (await api('/api/health')).json(); $('status').textContent=data.status==='ready' ? 'Mô hình sẵn sàng' : 'Chưa tải được mô hình'; $('status').classList.toggle('ready',data.status==='ready'); } catch { $('status').textContent='Mất kết nối API'; $('status').classList.remove('ready'); } }
checkHealth(); setInterval(checkHealth,30000);
window.addEventListener('pagehide',()=> {stopCamera();releaseImages();});
