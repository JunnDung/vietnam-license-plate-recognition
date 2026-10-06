'use strict';
let videoURL = null, videoRunning = false, videoGeneration = 0, videoNextIndex = 0, videoSampleFPS = 5, videoRows = [];
function stopVideo() {
  videoGeneration++; videoRunning = false; $('file-video').pause(); $('file-video').controls = true;
  $('video-stop').disabled = true; busyState(busy);
  if(videoURL && $('video-progress').value<1) {$('video-status').textContent += ' · Đã tạm dừng';$('video-start').textContent='Tiếp tục';}
}
function clearVideo() {
  stopVideo(); if(videoURL) URL.revokeObjectURL(videoURL); videoURL = null; videoNextIndex = 0; videoRows = [];
  $('file-video').removeAttribute('src'); $('file-video').load(); $('file-video').hidden = true;
  $('video-body').replaceChildren(); $('video-results').hidden = true; $('video-export').disabled = true;
  $('results').replaceChildren(element('p','hint','Chờ nhận diện khung mới.')); $('video-status').textContent='Chưa chọn video.';
  $('video-fps').disabled = false; $('video-progress').value = 0; $('video-start').textContent = 'Phân tích video'; busyState(busy);
}
function videoEvent(video, event, action) {
  return new Promise((resolve,reject)=> {
    const clean = ()=> {clearTimeout(timer);video.removeEventListener(event,done);video.removeEventListener('error',fail);};
    const done = ()=> {clean();resolve();}, fail = ()=> {clean();reject(new Error('Trình duyệt không đọc được video. Thử MP4 H.264 hoặc WebM VP8/VP9, hoặc dùng CLI.'));};
    const timer = setTimeout(()=>{clean();reject(new Error('Đọc khung video quá lâu. Thử video khác hoặc dùng CLI.'));},15000);
    video.addEventListener(event,done,{once:true}); video.addEventListener('error',fail,{once:true}); action();
  });
}
async function seekVideo(time) {
  const video = $('file-video'); video.pause();
  if(Math.abs(video.currentTime-time)<.001 && video.readyState>=2) return;
  await videoEvent(video,'seeked',()=> {video.currentTime=time;});
}
function addVideoRows(time,data) {
  for(const item of data.detections) {
    videoRows.push({time,plate:item.plate,ocr:item.ocr_confidence,review:item.needs_review});
    const row=element('tr'), action=element('td'), view=element('button','','Xem');
    row.append(element('td','',item.display_plate || 'Chưa đọc được'),element('td','',time.toFixed(2)),element('td','',`${(item.ocr_confidence*100).toFixed(1)}%`),element('td','',item.needs_review ? 'Cần kiểm tra' : 'Đã đọc'));
    view.addEventListener('click',async()=> {
      if(busy) {notice('Chờ lượt đang xử lý xong trước khi xem khung.');return;}
      stopVideo(); const generation=videoGeneration;
      try {await seekVideo(time);if(generation===videoGeneration){draw(frameCanvas($('file-video')),data.detections);renderResults(data);$('frame-caption').textContent=`Khung tại ${time.toFixed(2)} giây video`;}}
      catch(error){notice(error.message,true);}
    });
    action.append(view); row.append(action); $('video-body').append(row);
    if($('video-body').children.length>100) $('video-body').firstElementChild.remove();
  }
  $('video-export').disabled = !videoRows.length;
}
$('video-file').addEventListener('change',async event=> {
  const file=event.target.files[0];if(!file) return;
  if(busy) {notice('Chờ xử lý xong trước khi đổi video.');event.target.value='';return;}
  if(file.size>500*1024*1024 || !/\.(mp4|webm|ogv)$/i.test(file.name)) {notice('Chọn MP4, WebM hoặc OGV tối đa 500 MB.',true);event.target.value='';return;}
  stopCamera(); clearVideo(); selectedFile=null; videoURL=URL.createObjectURL(file);const generation=videoGeneration,video=$('file-video');
  $('video-status').textContent='Đang đọc video…';
  try {
    await videoEvent(video,'loadeddata',()=>{video.src=videoURL;video.load();});
    if(generation!==videoGeneration) return;
    if(!Number.isFinite(video.duration) || video.duration<=0 || video.duration>600 || Math.min(video.videoWidth,video.videoHeight)<32) throw new Error('Video cần dài tối đa 10 phút, kích thước ít nhất 32 px và có thời lượng xác định.');
    video.hidden=false; draw(video); $('frame-caption').textContent='Khung xem trước · chưa phân tích'; $('filename').textContent=`${file.name} · ${video.duration.toFixed(1)} giây`;
    $('video-status').textContent='Video đã sẵn sàng. Bấm Phân tích video để quét từ đầu.'; $('video-results').hidden=false; busyState(false);
  } catch(error) {if(generation===videoGeneration){clearVideo();$('video-status').textContent=error.message;notice(error.message,true);}}
});
$('video-stop').addEventListener('click',stopVideo);
$('video-start').addEventListener('click',async()=> {
  if(busy || videoRunning || !videoURL) return;
  stopCamera(); const generation=++videoGeneration, active=()=>videoRunning && generation===videoGeneration;
  const video=$('file-video');
  if($('video-progress').value===1) {videoNextIndex=0;videoRows=[];$('video-body').replaceChildren();$('video-export').disabled=true;$('video-progress').value=0;}
  videoSampleFPS=Number($('video-fps').value); videoRunning=true;video.pause();video.controls=false;
  $('video-fps').disabled=true;$('video-stop').disabled=false;$('video-start').disabled=true;$('camera-start').disabled=true;
  $('video-status').textContent=`Đang phân tích từ ${(videoNextIndex/videoSampleFPS).toFixed(1)} giây…`;
  const start=performance.now();let processed=0;
  try {
    while(active() && videoNextIndex/videoSampleFPS<video.duration-.0001) {
      const time=videoNextIndex/videoSampleFPS;await seekVideo(time);if(!active()) break;
      const frame=frameCanvas(video);if(!frame) throw new Error('Không lấy được khung video.');
      const blob=await new Promise(resolve=>frame.toBlob(resolve,'image/jpeg',.9));if(!blob) throw new Error('Không mã hóa được khung video.');
      const data=await processFile(blob,`video:${$('video-file').files[0].name.slice(0,40)}:${time.toFixed(2)}s`,frame,active,$('video-save').checked);
      if(!active()) break;if(!data) throw new Error('Đã dừng vì API không xử lý được khung video.');
      addVideoRows(time,data);videoNextIndex++;processed++;
      $('video-progress').value=Math.min(1,videoNextIndex/videoSampleFPS/video.duration);
      $('video-status').textContent=`${Math.min(video.duration,videoNextIndex/videoSampleFPS).toFixed(1)} / ${video.duration.toFixed(1)} giây · ${videoNextIndex} khung · ${videoRows.length} kết quả · ${(1000*processed/(performance.now()-start)).toFixed(1)} lượt/giây xử lý`;
      $('frame-caption').textContent=`Khung đã phân tích tại ${time.toFixed(2)} giây video`;
    }
    if(active()) {$('video-progress').value=1;$('video-status').textContent+=' · Hoàn tất';$('video-start').textContent='Quét lại';$('video-fps').disabled=false;}
  } catch(error) {if(active()) notice(error.message,true);}
  finally {if(generation===videoGeneration){videoRunning=false;video.controls=true;$('video-stop').disabled=true;busyState(false);if($('video-progress').value<1) $('video-start').textContent='Tiếp tục';}}
});
$('video-export').addEventListener('click',()=> {
  const safe=value=>{const text=String(value);return '"'+(/^[=+@\-\t\r\n]/.test(text) ? "'" : '')+text.replaceAll('"','""')+'"';};
  const csv='\ufeff'+[['video_seconds','plate','ocr_confidence','needs_review'],...videoRows.map(row=>[row.time.toFixed(2),row.plate,row.ocr,row.review])].map(row=>row.map(safe).join(',')).join('\r\n');
  const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})),anchor=element('a');anchor.href=url;anchor.download='video-plates.csv';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
