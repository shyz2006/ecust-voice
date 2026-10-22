/* Accounts: role-aware entries, admin account management and self-service password change. */
(()=>{'use strict';
 const $=id=>document.getElementById(id),esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const date=ts=>ts?new Date(ts*1000).toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric'}):'';
 const ROLE={admin:'管理员',user:'普通用户'};
 let me=null;
 async function api(path,method='GET',body){const response=await fetch(path,{method,headers:{'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});if(!(response.headers.get('content-type')||'').includes('application/json'))throw Error('登录已失效，请重新登录。');const data=await response.json();if(!response.ok||data.success===false)throw Error(data.message||'操作未完成，请稍后重试');return data;}
 function randomPassword(){const chars='abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789',bytes=crypto.getRandomValues(new Uint8Array(12));return Array.from(bytes,b=>chars[b%chars.length]).join('');}

 // 角色只决定显示哪些入口；权限以服务端校验为准。
 api('/api/auth/me').then(d=>{me=d;document.documentElement.dataset.role=d.role;const badge=$('accountBadge');badge.textContent=(d.role==='admin'?'管理员 · ':'')+d.username;badge.classList.toggle('is-admin',d.role==='admin');badge.hidden=false;}).catch(()=>{});

 function record(a){
  const server=a.source==='server',self=me&&a.username===me.username;
  const meta=[ROLE[a.role]||a.role,server?'服务器账号':'站内账号',a.disabled?'已停用':'',a.created_by?a.created_by+' 创建于 '+date(a.created_at):'',server?'':(a.last_login?'最近登录 '+date(a.last_login):'尚未登录')].filter(Boolean).join(' · ');
  const name=esc(a.username);
  const actions=server?'<span class="weekly-status">在服务器 .env 中维护</span>':self?'<span class="weekly-status">当前登录账号</span>':
   '<button type="button" data-acct-role="'+name+'" data-to="'+(a.role==='admin'?'user':'admin')+'">'+(a.role==='admin'?'设为普通用户':'设为管理员')+'</button>'+
   '<button type="button" data-acct-reset="'+name+'">重置密码</button>'+
   '<button type="button" data-acct-disable="'+name+'" data-to="'+(a.disabled?'0':'1')+'">'+(a.disabled?'启用':'停用')+'</button>'+
   '<button type="button" class="danger-action" data-acct-delete="'+name+'">删除</button>';
  return '<article class="record account-record'+(a.disabled?' is-disabled':'')+'"><div><strong>'+name+'</strong><p>'+esc(meta)+'</p></div><div class="record-actions">'+actions+'</div></article>';
 }
 async function fill(){
  $('accountCreateStatus').textContent='';
  try{const d=await api('/api/accounts');$('accountList').innerHTML=[...d.server,...d.site].map(record).join('')||'<p class="empty">还没有账号。</p>';}
  catch(e){$('accountList').innerHTML='<p class="error">'+esc(e.message)+'</p>';}
 }
 window.CampusAccounts={fill};

 $('accountGenerate').onclick=()=>{$('accountCreateForm').elements.password.value=randomPassword();};
 $('accountCreateForm').onsubmit=async e=>{
  e.preventDefault();const f=e.currentTarget,b=f.querySelector('button.primary'),body=Object.fromEntries(new FormData(f).entries());
  body.username=body.username.trim();b.disabled=true;
  try{await api('/api/accounts','POST',body);f.reset();await fill();$('accountCreateStatus').textContent='已创建 '+body.username+'（'+ROLE[body.role]+'），请把初始密码告知对方';}
  catch(err){$('accountCreateStatus').textContent=err.message;}finally{b.disabled=false;}
 };
 $('accountList').addEventListener('click',async e=>{
  const b=e.target.closest('button');if(!b)return;
  const status=t=>{$('accountCreateStatus').textContent=t;};
  try{
   if(b.dataset.acctRole){const user=b.dataset.acctRole;await api('/api/accounts/'+encodeURIComponent(user),'PATCH',{role:b.dataset.to});await fill();status(user+' 已设为'+ROLE[b.dataset.to]);}
   else if(b.dataset.acctDisable){const user=b.dataset.acctDisable,off=b.dataset.to==='1';await api('/api/accounts/'+encodeURIComponent(user),'PATCH',{disabled:off});await fill();status(user+(off?' 已停用，已登录的设备会退出':' 已启用'));}
   else if(b.dataset.acctDelete){const user=b.dataset.acctDelete;if(!confirm('删除账号 '+user+'？删除后无法恢复，该账号的研究记录仍会保留。'))return;await api('/api/accounts/'+encodeURIComponent(user),'DELETE');await fill();status(user+' 已删除');}
   else if(b.dataset.acctReset){const user=b.dataset.acctReset,actions=b.closest('.record-actions');actions.innerHTML='<form class="account-reset" data-user="'+esc(user)+'"><input name="password" type="text" autocomplete="new-password" minlength="8" maxlength="128" required placeholder="新密码（至少8位）" aria-label="'+esc(user)+' 的新密码"><button type="button" data-reset-random>随机</button><button class="primary">确认</button><button type="button" data-reset-cancel>取消</button></form>';actions.querySelector('input').focus();}
   else if('resetRandom' in b.dataset){b.form.elements.password.value=randomPassword();}
   else if('resetCancel' in b.dataset){await fill();}
  }catch(err){status(err.message);}
 });
 $('accountList').addEventListener('submit',async e=>{
  e.preventDefault();const f=e.target,user=f.dataset.user;
  try{await api('/api/accounts/'+encodeURIComponent(user),'PATCH',{password:f.elements.password.value});await fill();$('accountCreateStatus').textContent=user+' 的密码已重置，请把新密码告知对方';}
  catch(err){$('accountCreateStatus').textContent=err.message;}
 });

 $('accountBadge').onclick=()=>{
  const f=$('passwordForm'),server=!me||me.source!=='site';f.reset();$('passwordStatus').textContent='';
  $('passwordIntro').textContent=server?'当前账号由服务器配置管理，如需修改密码请联系管理员。':'修改后，其他设备上的登录会失效。';
  f.querySelectorAll('input,button.primary').forEach(x=>x.disabled=server);
  $('passwordDialog').showModal();
 };
 $('passwordForm').onsubmit=async e=>{
  e.preventDefault();const f=e.currentTarget,b=f.querySelector('button.primary'),v=Object.fromEntries(new FormData(f).entries());
  if(v.new_password!==v.confirm_password){$('passwordStatus').textContent='两次输入的新密码不一致';return;}
  b.disabled=true;
  try{await api('/api/account/password','POST',{current_password:v.current_password,new_password:v.new_password});f.reset();$('passwordStatus').textContent='密码已修改';}
  catch(err){$('passwordStatus').textContent=err.message;}finally{b.disabled=false;}
 };
})();
