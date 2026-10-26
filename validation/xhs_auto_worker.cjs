// Isolated extension API fixtures; never controls an installed user browser.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('browser-tools/xhs-visible/background.js','utf8');
const manifest=JSON.parse(fs.readFileSync('browser-tools/xhs-visible/manifest.json','utf8'));
assert(!manifest.permissions.includes('cookies'));assert(!manifest.permissions.includes('debugger'));assert(!manifest.host_permissions.includes('<all_urls>'));
async function scenario(blocked=false,borrowed=false,noMatch=false){
 let state=borrowed?{ownedTab:7}:{},alarm,listener,onAlarm,onStartup,requests=[],closed=[],created=[],scheduled=0,clock=Date.now();
 const active={id:7,status:'complete',url:'https://www.xiaohongshu.com/search_result?keyword=%E5%8D%8E%E7%90%86'};
 const chrome={storage:{local:{get:async()=>({...state}),set:async x=>Object.assign(state,x),remove:async key=>{delete state[key];}}},
  alarms:{get:async()=>alarm,clear:async()=>{alarm=undefined;},create:async(name,o)=>{scheduled++;alarm={name,...o,scheduledTime:clock+o.delayInMinutes*60000};},onAlarm:{addListener:f=>onAlarm=f}},
  runtime:{id:'test-extension',onStartup:{addListener:f=>onStartup=f},onInstalled:{addListener:()=>{}},onMessage:{addListener:f=>listener=f}},
  action:{setBadgeText:async()=>{}},tabs:{query:async()=>borrowed?[active]:[],create:async options=>{created.push(options);return {id:7};},get:async()=>borrowed?active:({id:7,status:'complete',url:created.at(-1).url}),remove:async id=>closed.push(id)},
  scripting:{executeScript:async options=>options.files?[]:[{result:blocked?{blocked:true}:noMatch?{error:'读取到3个链接，匹配0条',diagnostics:{links:3,cards:2,titles:2,school_matches:0}}:{data:{format:'ecust-xhs-visible-v1',items:[{title:'华理校园'}]}}}]}};
 const context=vm.createContext({chrome,console,AbortController,URL,Date:class extends Date{static now(){return clock;}},setTimeout:(f,ms)=>setTimeout(f,ms===1500?0:ms),clearTimeout,fetch:async(url,options)=>{requests.push({url,options});return {ok:true,headers:{get:()=> 'application/json'},json:async()=>({success:true,received:1,added:1})};}});
 vm.runInContext(source,context);
 const send=message=>new Promise(resolve=>listener(message,{id:'test-extension'},resolve));
 const token='ecust_xhs_'+'a'.repeat(43);assert((await send({action:'connect',token,hours:6})).success);
 for(let n=0;n<100&&!['complete','paused'].includes(state.last?.state);n++)await new Promise(r=>setTimeout(r,5));
 assert.equal(state.last.state,blocked||noMatch?'paused':'complete');
 if(noMatch){assert.equal(state.last.diagnostics.links,3);assert(state.last.message.includes('读取到3个链接'));assert.equal(requests.filter(r=>r.url.endsWith('/push')).length,0);return 'no_match_preserves_read_diagnostics';}
 if(borrowed){assert.equal(created.length,0);assert.equal(closed.length,0);assert(!state.ownedTab);await send({action:'pause'});clock+=6*60000;await send({action:'sync-current'});for(let n=0;n<100&&requests.filter(r=>r.url.endsWith('/push')).length<2;n++)await new Promise(r=>setTimeout(r,5));assert.equal(requests.filter(r=>r.url.endsWith('/push')).length,2);assert.equal(state.enabled,false);assert.equal(closed.length,0);return 'resume_and_manual_upload_preserve_current_page';}
 if(blocked){assert.equal(state.enabled,false);assert.equal(requests.filter(r=>r.url.endsWith('/push')).length,0);assert.equal(closed.length,0);assert(!alarm);}
 else{
  assert.equal(state.enabled,true);assert.equal(closed.length,1);assert.equal(alarm.periodInMinutes,360);
  const push=requests.find(r=>r.url.endsWith('/push'));assert.equal(push.options.credentials,'omit');assert.equal(push.options.headers.Authorization,'Bearer '+token);
  assert(!JSON.stringify(await send({action:'state'})).includes(token));
  assert(!(await send({action:'run'})).success);
  onStartup();await new Promise(r=>setTimeout(r,10));assert.equal(scheduled,1);assert.equal(created.length,1);
  clock+=6*3600000;onAlarm({name:'ecust-xhs-sync'});
  for(let n=0;n<100&&created.length<2;n++)await new Promise(r=>setTimeout(r,5));
  for(let n=0;n<100&&state.last.state!=='complete';n++)await new Promise(r=>setTimeout(r,5));
  assert.equal(created.length,2);assert.notEqual(created[0].url,created[1].url);
  await send({action:'pause'});assert.equal(state.enabled,false);assert(!alarm);
 }
 return blocked?'verification_pauses_without_upload':'alarm_rotates_uploads_and_preserves_schedule';
}
(async()=>{const result={passed:true,fixture_only:true,checks:[await scenario(),await scenario(true),await scenario(false,true),await scenario(false,false,true)],real_user_capture_verified:false};fs.writeFileSync('validation/xhs-auto-worker-results.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));})().catch(e=>{console.error(e);process.exit(1);});
