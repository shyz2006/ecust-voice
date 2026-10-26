(()=>{'use strict';const button=document.getElementById('capture'),status=document.getElementById('status'),download=document.getElementById('download');
const el=id=>document.getElementById(id);let initialized=false;
async function send(message){const result=await chrome.runtime.sendMessage(message);if(!result?.success)throw Error(result?.message||'助手尚未就绪');return result;}
async function refresh(){try{const s=await send({action:'state'});if(!initialized){el('hours').value=String(s.hours);initialized=true;}el('run').hidden=!s.enabled;el('pause').hidden=!s.enabled;el('connect').textContent=s.enabled?'保存同步设置':s.paired?'恢复自动同步':'连接并开启自动同步';el('autoStatus').textContent=(s.enabled?'自动同步已开启':'自动同步未运行')+(s.last?' · '+s.last.message:'')+(s.alarm?.scheduledTime?' · 下次 '+new Date(s.alarm.scheduledTime).toLocaleString('zh-CN'):'');if(s.paired)el('token').placeholder='已保存同步码，留空沿用';}catch(e){el('autoStatus').textContent=e.message;}}
for(const [id,action] of [['connect','connect'],['pause','pause'],['run','run']])el(id).onclick=async()=>{el(id).disabled=true;try{await send({action,token:el('token').value,hours:el('hours').value});el('token').value='';await refresh();}catch(e){el('autoStatus').textContent=e.message;}finally{el(id).disabled=false;}};
refresh();setInterval(refresh,3000);
button.onclick=async()=>{button.disabled=true;status.textContent='正在读取已加载的卡片…';try{
 const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
 if(!tab?.id||!/^https:\/\/(www\.)?xiaohongshu\.com\/search_result(?:[/?]|$)/.test(tab.url||''))throw Error('请先切换到小红书“华理”的搜索结果页');
 await chrome.scripting.executeScript({target:{tabId:tab.id},files:['collector.js']});
 const result=await chrome.scripting.executeScript({target:{tabId:tab.id},func:()=>{try{return {data:globalThis.EcustXhsCollector.extract()};}catch(e){return {error:e.message};}}});
 const value=result[0]?.result;if(!value?.data)throw Error(value?.error||'读取未完成，请刷新搜索页后重试');
 const data=value.data,blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
 download.href=URL.createObjectURL(blob);download.download='ecust-xhs-'+new Date(data.captured_at*1000).toISOString().slice(0,10)+'.json';download.hidden=false;button.hidden=true;
 status.textContent='已读取 '+data.items.length+' 条。下载后，在校园平台“配置 → 检索与采集”中同步。';
 const list=document.getElementById('preview');for(const item of data.items.slice(0,5)){const li=document.createElement('li');li.textContent=item.title;list.append(li);}
 }catch(error){status.textContent=error.message;button.disabled=false;}};
})();