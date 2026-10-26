/* Ordinary browser pages only. Platform verification stops automatic collection. */
const ORIGIN='https://smydashuaige.2026515.xyz',ALARM='ecust-xhs-sync';
const QUERIES=['华理','华东理工大学','华理 奉贤','华理 徐汇'];
let running=false;
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function stored(){return chrome.storage.local.get(['token','enabled','hours','index','last','leaseUntil','ownedTab']);}
async function api(path,token,body){
 const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),20000);
 try{const response=await fetch(ORIGIN+'/pulse/api/xhs-browser/'+path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{}),credentials:'omit',redirect:'error',signal:ctrl.signal});
  if(!response.headers.get('Content-Type')?.includes('application/json'))throw Error('同步连接已失效，请重新连接校园平台');
  const value=await response.json();if(!response.ok||!value.success)throw Error(value.message||'校园平台暂未接收');return value;
 }finally{clearTimeout(timer);}
}
async function schedule(){const s=await stored(),old=await chrome.alarms.get(ALARM),minutes=Math.max(360,(s.hours||6)*60);if(!s.enabled||!s.token){await chrome.alarms.clear(ALARM);return;}if(!old||old.periodInMinutes!==minutes)await chrome.alarms.create(ALARM,{delayInMinutes:minutes,periodInMinutes:minutes});}
async function result(state,message,extra={}){await chrome.storage.local.set({last:{state,message,at:Date.now(),...extra}});await chrome.action.setBadgeText({text:state==='paused'?'!':state==='complete'?'✓':''});}
async function closeOwned(id){try{const tab=await chrome.tabs.get(id);if(/^https:\/\/(www\.)?xiaohongshu\.com\/search_result(?:[/?]|$)/.test(tab.url||''))await chrome.tabs.remove(id);}catch{}await chrome.storage.local.remove('ownedTab');}
async function run(){
 const settings=await stored();if(running||!settings.enabled||!settings.token||(settings.leaseUntil||0)>Date.now())return;
 running=true;let tab,keep=false;
 await chrome.storage.local.set({leaseUntil:Date.now()+5*60000});
 try{
  if(settings.ownedTab)await closeOwned(settings.ownedTab);
  await result('running','正在打开华理公开搜索页');
  const query=QUERIES[(settings.index||0)%QUERIES.length];
  tab=await chrome.tabs.create({url:'https://www.xiaohongshu.com/search_result?keyword='+encodeURIComponent(query),active:false});
  await chrome.storage.local.set({ownedTab:tab.id});let data;
  for(let round=0;round<12;round++){
   await wait(1500);const current=await chrome.tabs.get(tab.id);
   if(current.status!=='complete')continue;
   if(!/^https:\/\/(www\.)?xiaohongshu\.com\/search_result(?:[/?]|$)/.test(current.url||''))throw Error('搜索页需要确认，请在小红书完成登录或验证');
   await chrome.scripting.executeScript({target:{tabId:tab.id},files:['collector.js']});
   const response=await chrome.scripting.executeScript({target:{tabId:tab.id},func:()=>{
    if(/安全限制|安全验证|访问受限|扫码登录|请先登录|验证码/.test((document.body.innerText||'').slice(0,12000)))return {blocked:true};
    try{return {data:globalThis.EcustXhsCollector.extract()};}catch(e){return {error:e.message};}
   }});
   const value=response[0]?.result;if(value?.blocked)throw Error('小红书需要登录或安全验证，请处理后手动恢复');
   if(value?.data){data=value.data;break;}
  }
  if(!data)throw Error('搜索页尚无可读取的华理卡片，请检查页面后手动恢复');
  if(!(await stored()).enabled)return;
  const uploaded=await api('push',settings.token,data);
  await chrome.storage.local.set({index:((settings.index||0)+1)%QUERIES.length});
  await result('complete','已同步 '+uploaded.received+' 条华理笔记，其中新增 '+uploaded.added+' 条',{received:uploaded.received});
 }catch(error){
  keep=true;await chrome.storage.local.set({enabled:false});await chrome.alarms.clear(ALARM);
  await result('paused',error.name==='AbortError'?'网络请求未确认，自动同步已暂停；请检查平台最近同步时间后恢复':String(error.message||'同步中断，请检查连接后恢复'));
 }finally{
  if(tab&&!keep)await closeOwned(tab.id);
  await chrome.storage.local.remove('leaseUntil');running=false;
 }
}
chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name===ALARM)void run();});
chrome.runtime.onStartup.addListener(()=>{void (async()=>{await schedule();const s=await stored();if(s.enabled&&Date.now()-(s.last?.at||0)>=(s.hours||6)*3600000)void run();})();});
chrome.runtime.onInstalled.addListener(()=>{void schedule();});
chrome.runtime.onMessage.addListener((message,sender,sendResponse)=>{
 if(sender.id!==chrome.runtime.id)return false;
 (async()=>{
  const state=await stored();
  if(message.action==='state')return {success:true,enabled:!!state.enabled,paired:!!state.token,hours:state.hours||6,last:state.last,alarm:await chrome.alarms.get(ALARM)};
  if(message.action==='connect'){
   const token=(message.token||state.token||'').trim();if(!/^ecust_xhs_[A-Za-z0-9_-]{40,80}$/.test(token))throw Error('请粘贴校园平台生成的同步码');
   const hours=Number(message.hours);if(!Number.isInteger(hours)||hours<6||hours>24)throw Error('同步间隔请选择6至24小时');
   await api('ping',token);await chrome.storage.local.set({token,enabled:true,hours});await schedule();if(!state.enabled)void run();return {success:true};
  }
  if(message.action==='pause'){await chrome.storage.local.set({enabled:false});await chrome.alarms.clear(ALARM);return {success:true};}
  if(message.action==='run'){if(!state.enabled)throw Error('请先连接并开启自动同步');if(state.last?.state==='complete'&&Date.now()-state.last.at<300000)throw Error('刚刚已同步，五分钟后可再手动运行');void run();return {success:true};}
  throw Error('操作未识别');
 })().then(sendResponse,error=>sendResponse({success:false,message:error.name==='AbortError'?'连接超时，请稍后再试':error.message}));
 return true;
});
