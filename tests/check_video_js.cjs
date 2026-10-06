// Controller check without browser/hardware: sampling, cancellation and replay at a new rate.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const nodes=new Map();
function node(id='') {
  const value={id,value:0,checked:false,disabled:false,textContent:'',children:[],handlers:{},
    addEventListener(event,handler){this.handlers[event]=handler;},removeEventListener(event){delete this.handlers[event];},
    append(...children){this.children.push(...children);},replaceChildren(){this.children=[];},pause(){},load(){},
    removeAttribute(){},remove(){},click(){},controls:true,readyState:2,duration:1,videoWidth:64,videoHeight:48};
  let time=0;Object.defineProperty(value,'currentTime',{get:()=>time,set:next=>{time=next;queueMicrotask(()=>value.handlers.seeked?.());}});
  return value;
}
const $=id=>{if(!nodes.has(id)) nodes.set(id,node(id));return nodes.get(id);};
$('video-fps').value='5';$('video-file').files=[{name:'public.webm'}];
const calls=[],notices=[];let pending=null,hold=false;
const context={$,setTimeout,clearTimeout,performance,URL,Blob,crypto:require('node:crypto').webcrypto,selectedFile:null,busy:false,
  element:()=>node(),notice:message=>notices.push(message),stopCamera(){},draw(){},renderResults(){},
  frameCanvas:()=>({toBlob:callback=>callback(new Blob(['frame']))}),
  busyState(value){context.busy=value;},
  async processFile(blob,source,image,active,save) {
    context.busy=true;calls.push({source,save});
    if(hold) await new Promise(resolve=>pending=resolve);
    context.busy=false;
    return active() ? {detections:[{plate:'51A12345',display_plate:'51A-123.45',ocr_confidence:.95,needs_review:false}]} : null;
  }};
vm.createContext(context);vm.runInContext(fs.readFileSync('web/video.js','utf8'),context);
vm.runInContext("videoURL='blob:demo'",context);
(async()=>{
  await $('video-start').handlers.click();
  assert.deepEqual(calls.map(call=>Number(call.source.split(':').at(-1).slice(0,-1))),[0,.2,.4,.6,.8]);
  assert(calls.every(call=>call.save===false));assert.equal($('video-body').children.length,5);assert.equal($('video-progress').value,1);
  $('video-fps').value='2';calls.length=0;await $('video-start').handlers.click();
  assert.equal(calls.length,2);assert.equal($('video-body').children.length,2);
  calls.length=0;hold=true;const running=$('video-start').handlers.click();
  while(!pending) await new Promise(resolve=>setTimeout(resolve,1));
  await $('video-start').handlers.click();assert.equal(calls.length,1,'No second request while busy');
  context.stopVideo();pending();await running;
  assert.equal($('video-progress').value,0);assert.equal($('video-start').textContent,'Tiếp tục');
  assert.equal($('video-body').children.length,0,'Stopped response must not add stale rows');
  assert.equal(vm.runInContext('videoNextIndex',context),0,'Stopped frame is retried on resume');
  hold=false;calls.length=0;await $('video-start').handlers.click();assert.equal(calls.length,2);
  vm.runInContext("videoRows=[];videoEvents.clear()",context);$('video-body').replaceChildren();
  const stable={detections:[{plate:'51A12345',display_plate:'51A-123.45',ocr_confidence:.95,needs_review:false,temporal:{track_id:'same',status:'stable'}}]};
  context.addVideoRows(0,stable);context.addVideoRows(.2,stable);
  assert.equal($('video-body').children.length,1,'A stable plate track must be grouped');
  assert.equal(vm.runInContext('videoRows[0].frames',context),2);
  context.addVideoRows(.4,{detections:[{...stable.detections[0],temporal:{track_id:'pending',status:'pending'}}]});
  assert.equal($('video-body').children.length,1,'Unstable tracks must not enter stable CSV/events');
  let exported=null;context.URL={createObjectURL(blob){exported=blob;return 'blob:csv';},revokeObjectURL(){}};
  $('video-export').handlers.click();
  const csv=await exported.text();
  assert(csv.includes('first_stable_seconds'));assert.equal(csv.trim().split('\r\n').length,2,'Grouped CSV contains one event');
  assert(csv.includes('"0.00","0.20","51A12345"'));
  assert.equal(notices.length,0);console.log('PASS: exact video timestamps, no implicit saving, cancellation, no overlapping requests and replay with a different FPS.');
})().catch(error=>{console.error(error);process.exitCode=1;});
