'use strict';
let recognitionRegion = null;
// Whole-frame detail is a heuristic; it does not measure plate readability.
function frameSharpness(frame) {
  const probe = document.createElement('canvas');
  probe.width = Math.min(320, frame.width); probe.height = Math.max(3, Math.round(frame.height * probe.width / frame.width));
  const context = probe.getContext('2d', {willReadFrequently: true}); context.drawImage(frame, 0, 0, probe.width, probe.height);
  const pixels = context.getImageData(0, 0, probe.width, probe.height).data, width = probe.width, height = probe.height;
  const gray = new Float32Array(width * height), smooth = new Float32Array(width * height);
  for (let i = 0; i < gray.length; i++) gray[i] = .299 * pixels[4*i] + .587 * pixels[4*i+1] + .114 * pixels[4*i+2];
  for (let y = 1; y < height-1; y++) for (let x = 1; x < width-1; x++) {
    const i = y*width+x;
    smooth[i] = (gray[i-width-1]+2*gray[i-width]+gray[i-width+1]+2*gray[i-1]+4*gray[i]+2*gray[i+1]+gray[i+width-1]+2*gray[i+width]+gray[i+width+1])/16;
  }
  let total = 0, squares = 0, count = 0;
  for (let y = 2; y < height-2; y++) for (let x = 2; x < width-2; x++) {
    const i = y*width+x, value = smooth[i-1]+smooth[i+1]+smooth[i-width]+smooth[i+width]-4*smooth[i];
    total += value; squares += value*value; count++;
  }
  return count ? squares/count-(total/count)**2 : 0;
}
function frameCanvas(video) {
  const region = recognitionRegion || [0,0,100,100];
  const [x,y,width,height] = region.map((value,index)=>value/100*(index%2===0 ? video.videoWidth : video.videoHeight));
  const frame = document.createElement('canvas'), scale = Math.min(1,1280/Math.max(width,height));
  frame.width = Math.round(width*scale); frame.height = Math.round(height*scale);
  if (!frame.width || !frame.height) return null;
  frame.getContext('2d').drawImage(video,x,y,width,height,0,0,frame.width,frame.height);
  return frame;
}
function frameDelay(start, fps) { return Math.max(0,1000/fps-(performance.now()-start)); }
async function captureBestFrame(video, active) {
  let best = null, score = -1;
  for (let i = 0; i < 3; i++) {
    if (!active()) return null;
    const frame = frameCanvas(video);
    if (!frame) return null;
    const candidateScore = frameSharpness(frame);
    if (candidateScore > score) { best = frame; score = candidateScore; }
    if (i < 2) await new Promise(resolve => setTimeout(resolve, 33));
  }
  return active() ? best : null;
}
