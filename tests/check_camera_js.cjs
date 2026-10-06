// Runnable without a camera: known pixel patterns, best-frame choice and cancellation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const width = 64, height = 48;
function pattern(contrast) {
  const values = new Uint8ClampedArray(width*height*4);
  for (let y=0; y<height; y++) for (let x=0; x<width; x++) {
    const i=(y*width+x)*4, value=128+(((x>>2)+(y>>2))%2 ? contrast : -contrast);
    values[i]=values[i+1]=values[i+2]=value; values[i+3]=255;
  }
  return values;
}
const clear = pattern(100), blurred = pattern(10), frames = [blurred, clear, blurred];
const video = {videoWidth:width, videoHeight:height, frames};
const context = {setTimeout, performance:{now:()=>150}, document:{createElement() {
  const canvas = {width:0,height:0,pixels:null};
  canvas.getContext = ()=>({drawImage(source) {canvas.pixels=source.frames ? source.frames.shift() : source.pixels;},
                            getImageData(){return {data:canvas.pixels};}});
  return canvas;
}}};
vm.createContext(context);vm.runInContext(fs.readFileSync('web/camera.js','utf8'),context);
(async()=>{
  assert(context.frameSharpness({width,height,pixels:clear})>context.frameSharpness({width,height,pixels:blurred}));
  const selected=await context.captureBestFrame(video,()=>true);
  assert.equal(selected.pixels,clear);
  assert.equal(await context.captureBestFrame(video,()=>false),null);
  assert.equal(context.frameDelay(100,5),150);
  assert.equal(context.frameDelay(0,10),0);
  assert.equal(context.frameCanvas({videoWidth:1920,videoHeight:1080,frames:[clear]}).width,1280);
  vm.runInContext('recognitionRegion=[25,25,50,50]',context);
  const cropped=context.frameCanvas({videoWidth:1920,videoHeight:1080,frames:[clear]});
  assert.equal(cropped.width,960);assert.equal(cropped.height,540);
  console.log('PASS: burst, cancellation, bounded frame size and target-rate timing without extra processing delay.');
})().catch(error=>{console.error(error);process.exitCode=1;});
