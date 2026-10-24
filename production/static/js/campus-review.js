/* Campus review: six focused modules share one category and evidence model. */
(()=>{'use strict';
const $=id=>document.getElementById(id),esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=value=>value==null?'—':Number(value).toLocaleString('zh-CN'),date=ts=>ts?new Date(ts*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'—';
const shortDate=ts=>new Date(ts*1000).toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric'});
const DAY=86400,NAMES={'xiaohongshu-school':'小红书华理讨论（搜索摘要）','douyin-school':'抖音华理讨论（搜索摘要）','xiaohongshu':'小红书','huyou-school':'狐友华理圈','tieba-school':'华理贴吧','douyin':'抖音','thepaper':'澎湃','bilibili-hot-search':'B站热搜','bilibili-popular':'B站热门','toutiao':'头条','weibo':'微博','baidu':'百度'};
const state={tab:'campus',overview:null,hot:null,memes:null,hotPlatform:'抖音',ledger:null,modalVersion:0,task:null,poll:null,overviewPromise:null};
let noticeTimer;
function notice(message){$('notice').textContent=message;$('notice').hidden=false;clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>$('notice').hidden=true,6500);}
async function api(url,options={}){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
 try{const response=await fetch(url,{...options,signal:controller.signal,headers:{'Content-Type':'application/json',...(options.headers||{})}});if(!(response.headers.get('content-type')||'').includes('application/json'))throw Error(response.redirected?'登录已失效，请重新登录。':'服务暂时不可用，请稍后重试。');const data=await response.json();if(!response.ok||data.success===false)throw Error(data.message||data.error||'读取失败，请稍后重试。');return data;}catch(error){if(error.name==='AbortError')throw Error('请求超时，请稍后重试。');throw error;}finally{clearTimeout(timer);}
}
const empty=text=>'<p class="empty">'+esc(text)+'</p>';
const errorState=(text,action)=>'<div class="empty error" role="alert">'+esc(text)+(action?'<br><button data-retry="'+esc(action)+'">重新读取</button>':'')+'</div>';
function safeUrl(url){try{const u=new URL(url);return ['http:','https:'].includes(u.protocol)?u.href:null;}catch{return null;}}
function sourceLink(url,label='打开原帖 ↗'){const safe=safeUrl(url);return safe?'<a href="'+esc(safe)+'" target="_blank" rel="noopener noreferrer">'+esc(label)+'</a>':'<span class="muted">原帖地址待补充</span>';}
function qs(values){return new URLSearchParams(Object.entries(values).filter(([,v])=>v!=null&&v!=='')).toString();}
async function overview(force=false){
 if(state.overview&&!force)return state.overview;
 if(state.overviewPromise)return state.overviewPromise;
 state.overviewPromise=api('/pulse/api/revision/overview').then(data=>{state.overview=data;return data;}).finally(()=>state.overviewPromise=null);
 return state.overviewPromise;
}
async function activate(tab){
 if(!['campus','trends','hot','memes','research','ledger'].includes(tab))tab='campus';
 state.tab=tab;document.querySelectorAll('.pane').forEach(p=>p.hidden=p.id!==tab);document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.tab===tab)));history.replaceState(null,'','#'+tab);
 try{if(tab==='campus'||tab==='trends'){await overview();renderCampus();renderTrends();}else if(tab==='hot'||tab==='memes')await loadFeed(tab);else if(tab==='ledger')await loadLedger();else await loadReports();}catch(error){const target={campus:'campusTopics',trends:'trendRows',hot:'hotFeed',memes:'memeFeed',ledger:'ledgerDonuts',research:'researchHistory'}[tab];$(target).innerHTML=errorState(error.message,tab);}
}
function renderCampus(){
 const data=state.overview;if(!data)return;
 $('homeSample').textContent=num(data.total_7d);$('campusUpdated').textContent='更新于 '+date(data.generated_at);$('practicePosts').querySelector('strong').textContent=num(data.practice_count);
 const count=Object.values(data.emotion||{}).reduce((s,v)=>s+v,0),negative=(data.emotion?.消极||0)/(count||1);
 const weather=!count?['○','等待样本','新采集的讨论将显示在这里。']:negative<.2?['☀','晴朗','多数表达平稳，关注同学的日常与收获。']:negative<.4?['☀','晴间多云','日常讨论中伴有一些困扰，值得倾听。']:['☁','多云','近期困扰表达较多，留意具体诉求。'];
 $('weather').innerHTML='<span class="weather-symbol" aria-hidden="true">'+weather[0]+'</span><div><div class="weather-title">校园心情 · '+weather[1]+'</div><p class="weather-caption">'+weather[2]+'</p></div><button class="text-button" style="margin-left:auto;font-size:11px;white-space:nowrap" data-method="emotion">计算口径 ↗</button>';
 const sorted=[...data.themes].sort((a,b)=>a.delta==null&&b.delta!=null?1:a.delta!=null&&b.delta==null?-1:a.delta!=null&&b.delta!=null?b.delta-a.delta||b.posts_24h-a.posts_24h:b.posts_24h-a.posts_24h).filter(t=>t.posts_24h>0).slice(0,3);
 $('campusTopics').innerHTML=sorted.map((t,i)=>'<article class="discussion"><span class="discussion-number">'+String(i+1).padStart(2,'0')+'</span><div><div class="discussion-head"><button data-theme="'+esc(t.theme)+'">'+esc(t.theme)+' ↗</button><span class="discussion-count">'+num(t.posts_24h)+' 篇新增帖 <span class="change">'+(t.delta==null?'':t.delta===0?'与前窗持平':(t.delta>0?'+':'')+num(t.delta)+' 较前窗')+'</span></span></div>'+(t.examples||[]).slice(0,3).map(p=>'<div class="discussion-excerpt">'+sourceLink(p.link,p.content.slice(0,95)+(p.content.length>95?'…':'')+' ↗')+'</div>').join('')+'</div></article>').join('')||empty('近24小时暂无新增讨论');
 $('campusCategories').innerHTML=data.themes.map(t=>'<button data-theme="'+esc(t.theme)+'"><span><i style="background:'+t.color+'"></i>'+esc(t.theme)+'</span><small>'+num(t.posts_7d)+' 篇 ↗</small></button>').join('');
}
function metric(label,value){return '<div class="metric"><span>'+esc(label)+'</span><strong>'+num(value)+'</strong></div>';}
function spark(points,color,width=160,height=35){
 const valid=points.map(p=>p.new_posts).filter(v=>v!=null),max=Math.max(1,...valid),step=(width-8)/Math.max(1,points.length-1);let path='',pen=false;
 points.forEach((p,i)=>{if(p.new_posts==null){pen=false;return;}path+=(pen?' L':' M')+(4+i*step).toFixed(1)+','+(height-5-p.new_posts/max*(height-10)).toFixed(1);pen=true;});
 return '<svg class="spark" viewBox="0 0 '+width+' '+height+'" aria-label="完整日窗新增帖走势"><path d="'+path+'" fill="none" stroke="'+color+'" stroke-width="1.8"/>'+points.map((p,i)=>p.new_posts==null?'<circle cx="'+(4+i*step)+'" cy="'+(height-5)+'" r="1.7" fill="#bac1b7"/>':'').join('')+'</svg>';
}
function renderTrends(){
 const d=state.overview;if(!d)return;const latest=d.themes.reduce((s,t)=>s+t.posts_24h,0);
 $('trendMetrics').innerHTML=metric('十日独立帖子',d.total)+metric('近24小时新增帖',latest)+metric('统一议题分类',d.themes.length)+metric('完整观测日窗',d.coverage.filter(c=>c.ready).length);
 $('trendScope').textContent=shortDate(d.window_start)+'—'+shortDate(d.generated_at);
 $('trendRows').innerHTML=d.themes.map(t=>'<tr><td><button data-theme-trend="'+esc(t.theme)+'"><i class="dot" style="background:'+t.color+'"></i>'+esc(t.theme)+'</button></td><td>'+spark(t.timeline,t.color)+'</td><td>'+num(t.posts_24h)+' 篇</td><td>'+(t.delta==null?'待完整采集':(t.delta>0?'+':'')+num(t.delta))+'</td><td>'+(t.reference.value==null?'资料待补齐':'约 '+num(Math.round(t.reference.value))+' 篇')+'</td><td><button data-theme-trend="'+esc(t.theme)+'">走势与原帖 ↗</button></td></tr>').join('');
 // 贴纸墙：大小随独立帖数，倾斜角由词本身决定（刷新不乱跳），热门词排在中间
 const words=d.wordcloud.slice(0,35),max=Math.max(1,...words.map(w=>w.df)),min=Math.min(max,...words.map(w=>w.df)),tones=['sun','lilac','peach','mint','sky','paper'];
 const scale=df=>max===min?0.5:Math.pow((df-min)/(max-min),0.75);
 const tilt=term=>{let h=7;for(const ch of term)h=(h*31+ch.codePointAt(0))%997;return (h%9-4)*0.9;};
 const centered=[];words.forEach((w,i)=>i%2?centered.push({w,i}):centered.unshift({w,i}));
 $('wordcloud').innerHTML=centered.map(({w,i})=>'<button class="word-chip tone-'+tones[i%tones.length]+'" data-word="'+esc(w.term)+'" style="--k:'+scale(w.df).toFixed(3)+';--tilt:'+tilt(w.term).toFixed(1)+'deg" title="'+esc(w.term)+' · '+w.df+' 篇独立帖">'+(i<3?'<i class="word-rank">'+(i+1)+'</i>':'')+esc(w.term)+'<small>'+num(w.df)+'</small></button>').join('')||empty('采集后将显示校园关键词');
}
function showDialog(title){
 const dialog=$('detailDialog');state.modalVersion++;$('detailTitle').textContent=title;$('detailBody').innerHTML=empty('正在读取…');if(!dialog.open)dialog.showModal();$('detailBody').scrollTop=0;return state.modalVersion;
}
function renderPosts(posts){return posts.map(p=>'<article class="post"><div class="post-head"><span>'+esc(NAMES[p.source]||p.source||p.platform||'平台来源')+' · '+date(p.published||p.ts)+(p.time_basis==='first_observed'?' · 首次采集':'')+'</span><span>'+esc(p.theme||p.crisis_level||'')+'</span></div><p>'+esc(p.content||p.title||'正文待补充')+'</p><div class="post-tags">'+esc(p.filter_reason||'')+(p.emotion?' · <button class="text-button" data-method="emotion">'+esc(p.emotion)+'表达</button>':'')+(p.heat!=null?' · <button class="text-button" data-method="heat">来源内互动分位 '+num(p.heat)+'</button>':'')+'</div>'+sourceLink(p.link||p.url)+'</article>').join('')||empty('当前范围暂无对应帖子');}
async function openPosts(params,title){const version=showDialog(title);try{const d=await api('/pulse/api/revision/posts?'+qs(params));if(version!==state.modalVersion)return;$('detailBody').innerHTML='<p class="muted">'+num(d.total)+' 条 · 按发布时间倒序</p>'+renderPosts(d.posts);}catch(e){if(version===state.modalVersion)$('detailBody').innerHTML=errorState(e.message);}}
function fullChart(t){
 const points=t.timeline,width=780,height=260,left=36,right=20,top=20,bottom=40,valid=points.map(p=>p.new_posts).filter(v=>v!=null),max=Math.max(4,...valid),nice=Math.ceil(max/4)*4,dx=(width-left-right)/9,y=v=>height-bottom-v/nice*(height-top-bottom);let path='',pen=false;
 points.forEach((p,i)=>{if(p.new_posts==null){pen=false;return;}path+=(pen?' L':' M')+(left+i*dx)+','+y(p.new_posts);pen=true;});
 return '<svg viewBox="0 0 '+width+' '+height+'" class="trend-chart" role="img" aria-label="'+esc(t.theme)+'十日新增帖走势">'+[0,1,2,3,4].map(i=>'<line x1="'+left+'" x2="'+(width-right)+'" y1="'+y(i*nice/4)+'" y2="'+y(i*nice/4)+'" stroke="#dde2d8"/><text x="'+(left-8)+'" y="'+(y(i*nice/4)+4)+'" text-anchor="end" fill="#78877c" font-size="11">'+i*nice/4+'</text>').join('')+'<path d="'+path+'" fill="none" stroke="'+t.color+'" stroke-width="2.5"/>'+points.map((p,i)=>'<g><text x="'+(left+i*dx)+'" y="'+(height-12)+'" text-anchor="middle" fill="#78877c" font-size="11">'+shortDate(p.ts+DAY)+'</text>'+(p.new_posts==null?'<text x="'+(left+i*dx)+'" y="'+(height-bottom-8)+'" text-anchor="middle" fill="#89968b" font-size="10">缺测</text>':'<circle cx="'+(left+i*dx)+'" cy="'+y(p.new_posts)+'" r="4" fill="'+t.color+'"><title>'+shortDate(p.ts)+' '+p.new_posts+' 篇</title></circle>')+'</g>').join('')+'</svg>';
}
async function openTrend(name){
 const version=showDialog(name+' · 走势与原帖');try{const d=await overview(),t=d.themes.find(x=>x.theme===name);if(!t)throw Error('议题不存在');const posts=await api('/pulse/api/revision/posts?'+qs({theme:name}));if(version!==state.modalVersion)return;
 $('detailBody').innerHTML='<div class="trend-summary"><span>十日 '+num(t.posts)+' 篇</span><span>近24h '+num(t.posts_24h)+' 篇</span><span>次日参考 '+(t.reference.value==null?'资料待补齐':'约 '+num(Math.round(t.reference.value))+' 篇')+'</span></div>'+fullChart(t)+'<p class="data-note">'+esc(t.reference.method)+'；'+t.reference.windows+' 个完整日窗。'+(t.reference.mae!=null?'历史滚动平均绝对误差 '+num(t.reference.mae)+' 篇（'+t.reference.validation_windows+' 窗）。':'历史误差待积累。')+'</p><h3 class="post-group-title">对应原帖 · '+num(posts.total)+' 条</h3>'+renderPosts(posts.posts);
 }catch(e){if(version===state.modalVersion)$('detailBody').innerHTML=errorState(e.message);}
}
async function loadCare(){
 try{const d=await api('/pulse/api/campus');const c=d.voice?.crisis||{};$('carePosts').querySelector('strong').textContent=num((c.高危||0)+(c.关注||0));}catch{$('carePosts').querySelector('strong').textContent='—';}
}
async function openCare(){const version=showDialog('心育关怀线索 · 原帖核查');try{const d=await api('/pulse/api/campus/crisis-posts?level=all');if(version!==state.modalVersion)return;$('detailBody').innerHTML='<p class="data-note">'+num(d.total)+' 条建议关怀，供人工结合原帖核查。</p>'+renderPosts(d.posts)+(d.filtered_posts?.length?'<h3 class="post-group-title">已过滤的日常表达 · '+num(d.filtered_total)+' 条</h3>'+renderPosts(d.filtered_posts):'');}catch(e){if(version===state.modalVersion)$('detailBody').innerHTML=errorState(e.message);}}
async function loadFeed(kind,force=false){
 if(kind==='memes'||!state[kind]||force)state[kind]=await api('/pulse/api/revision/feed/'+kind);
 const d=state[kind],current=state.hotPlatform;
 if(kind==='memes'){renderMemes(d);return;}
 $('hotPlatforms').innerHTML=d.platforms.map(p=>'<button data-feed="hot" data-platform="'+esc(p)+'" aria-selected="'+(p===current)+'">'+esc(p)+'</button>').join('');
 const items=d.items.filter(x=>x.platform===current).slice(0,10);
 $('hotFeed').innerHTML=items.map((x,i)=>`<article class="feed-card"><div class="feed-meta"><span class="feed-index">${String(i+1).padStart(2,'0')} · ${esc(x.platform)}</span><span>${date(x.ts)}</span></div><h2>${esc(x.title)}</h2>${signalPill(x.signal)}<div class="hot-focus"><h3>关注焦点</h3><p>${esc(x.focus||('话题要点：'+x.title))}</p></div><div class="feed-links">${sourceLink(x.url,'打开对应话题 ↗')}${sourceSearchUrl(x.platform,x.title)?sourceLink(sourceSearchUrl(x.platform,x.title),'站内搜索 ↗'):''}</div></article>`).join('')||empty(current==='小红书'?'当前小红书热榜源未返回有效榜单，暂无可展示数据。':'这个平台暂无可展示内容。');
}

function signalPill(signal){
 const flame='<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8.6 1.2c.5 2.6-2.9 3.7-2.9 7.1a2.4 2.4 0 0 0 .6 1.7C5 9.6 4.4 8.5 4.6 7.2 3.4 8.3 3 9.6 3 10.8 3 13.2 5.2 15 8 15s5-1.8 5-4.4c0-3.4-2.6-4.4-2.4-7-.9.5-1.6 1.4-1.8 2.5-.4-1.7-.1-3.4-.2-4.9z"/></svg>';
 if(signal==null)return '<p class="signal-sticker heat-pending" title="至少需要三次历史观测才计算升温">'+flame+'升温积累中</p>';
 const level=signal>=2?'hot':signal>=1?'warm':signal>0?'mild':'cool',value=Math.abs(signal).toFixed(1);
 return '<p class="signal-sticker heat-'+level+'" title="升温指数：与此前24小时排名相比的变化，数值越大升温越快">'+flame+(signal>0?'升温 <b>'+value+'</b>':'热度回落 <b>'+value+'</b>')+'</p>';
}
function sourceSearchUrl(platform,title){const prefix={'B站':'https://search.bilibili.com/all?keyword=','抖音':'https://www.douyin.com/search/','微博':'https://s.weibo.com/weibo?q=','百度':'https://www.baidu.com/s?wd='}[platform];return prefix?prefix+encodeURIComponent(title):null;}
function memeUseLink(p){
 const url=safeUrl(p.url);if(!url)return '';
 const bvid=new URL(url).pathname.match(/^\/video\/(BV[0-9A-Za-z]{10})(?:\/|$)/)?.[1];
 const search=sourceSearchUrl(p.platform,p.title);
 const copy=bvid||p.title;
 return '<div class="meme-use-row"><p><a class="meme-original" href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+esc((p.platform?p.platform+' · ':'')+p.title)+' ↗</a></p><div class="meme-use-actions">'+(search?sourceLink(search,p.platform+'搜索 ↗'):'')+'<button type="button" data-copy-meme="'+esc(copy)+'" title="'+(bvid?'复制后可在B站网站或App搜索':'复制标题后可在原平台查找')+'">'+(bvid?'复制 BV 号':'复制标题')+'</button></div></div>';
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-copy-meme]');if(!b)return;
 try{await navigator.clipboard.writeText(b.dataset.copyMeme);notice('已复制，可到原平台粘贴搜索。');}
 catch{showDialog('复制编号或标题');$('detailBody').innerHTML='<p>复制后可到原平台查找：</p><input class="copy-source-value" readonly value="'+esc(b.dataset.copyMeme)+'">';const input=$('detailBody').querySelector('input');input.focus();input.select();}
});

let memePoll;
function renderMemes(d){
 clearTimeout(memePoll);
 const seen=new Set(),cards=[...(d.items||[]).map(x=>({...x,confirmed:true})),...(d.candidates||[]).map(x=>({...x,confirmed:false}))].filter(x=>{const key=x.term.replace(/\s+/g,'').toLowerCase();if(seen.has(key)||!x.links?.length)return false;seen.add(key);return true;}).slice(0,10);
 $('memeFeed').innerHTML=cards.map((x,i)=>`<article class="feed-card meme-card ${x.confirmed?'confirmed':'discovered'}"><div class="feed-meta"><span class="feed-index">${String(i+1).padStart(2,'0')} · ${esc(x.form||'网络表达')}</span><span class="meme-status" title="${esc(x.confirmed?'已根据用例与释义资料核对':x.reason||'等待释义资料核对')}">${x.confirmed?'释义已核对':'新发现 · 用法观察'}</span></div><h2>${esc(x.term)}</h2><div class="meme-intro"><h3>简介</h3><p>${esc(x.confirmed?x.meaning:x.observation)}</p></div><div class="meme-uses"><h3>看看大家怎么用</h3>${x.links.slice(0,2).map(memeUseLink).join('')}</div></article>`).join('');
 if(d.running)memePoll=setTimeout(()=>{if(state.tab==='memes')loadFeed('memes',true).catch(e=>notice(e.message));},5000);
}


function donut(title,rows,total,action,unit='篇'){
 // 卡通甜甜圈：从大到小排列，段间留缝，墨线描边；悬停时中心显示该项占比
 const items=rows.filter(r=>r.value>0).sort((a,b)=>b.value-a.value),sum=items.reduce((n,r)=>n+r.value,0)||1;
 const C=2*Math.PI*50,gap=items.length>1?2.4:0,pct=v=>{const p=v/sum*100;return (p<10?p.toFixed(1):Math.round(p))+'%';};let offset=0;
 const segs=items.map((r,i)=>{const length=Math.max(0.8,C*r.value/sum-gap),el='<circle class="seg" data-i="'+i+'" cx="70" cy="70" r="50" stroke="'+r.color+'" stroke-dasharray="'+length.toFixed(2)+' '+(C-length).toFixed(2)+'" stroke-dashoffset="'+(-offset-gap/2).toFixed(2)+'" transform="rotate(-90 70 70)" role="button" tabindex="0" '+action(r)+' aria-label="'+esc(r.label)+' '+num(r.value)+' '+unit+'，占'+pct(r.value)+'"><title>'+esc(r.label)+' · '+num(r.value)+' '+unit+'</title></circle>';offset+=C*r.value/sum;return el;}).join('');
 const legend=items.map((r,i)=>'<button class="legend-row" data-i="'+i+'" data-label="'+esc(r.label)+'" data-pct="'+pct(r.value)+'" '+action(r)+'><i class="blob" style="background:'+r.color+'"></i><span class="legend-label">'+esc(r.label)+'</span><b>'+num(r.value)+'<small>'+pct(r.value)+'</small></b></button>').join('');
 return '<section class="donut-card"><h2>'+esc(title)+'</h2><div class="donut-visual"><svg viewBox="0 0 140 140"><circle class="donut-shadow" cx="73" cy="74" r="50"/><circle class="donut-track" cx="70" cy="70" r="50"/>'+segs+'<circle class="donut-rim" cx="70" cy="70" r="61"/><circle class="donut-rim" cx="70" cy="70" r="39"/><text class="donut-num" x="70" y="72" data-total="'+num(total)+'">'+num(total)+'</text><text class="donut-sub" x="70" y="87" data-sub="'+unit+' · 点击核查">'+unit+' · 点击核查</text></svg><div class="donut-legend">'+(legend||'<p class="empty">暂无数据</p>')+'</div></div></section>';
}
function focusDonut(card,i){
 card.classList.toggle('has-focus',i!=null);card.querySelectorAll('[data-i]').forEach(el=>el.classList.toggle('on',el.dataset.i===i));
 const big=card.querySelector('.donut-num'),sub=card.querySelector('.donut-sub'),row=i==null?null:card.querySelector('.legend-row[data-i="'+i+'"]');
 if(!big)return;big.textContent=row?row.dataset.pct:big.dataset.total;sub.textContent=row?row.dataset.label:sub.dataset.sub;
}
['mouseover','focusin'].forEach(type=>$('ledgerDonuts').addEventListener(type,e=>{const card=e.target.closest('.donut-card');if(card)focusDonut(card,e.target.closest('[data-i]')?.dataset.i??null);}));
['mouseout','focusout'].forEach(type=>$('ledgerDonuts').addEventListener(type,e=>{const card=e.target.closest('.donut-card');if(card&&!card.contains(e.relatedTarget))focusDonut(card,null);}));
function bars(rows,action){const max=Math.max(1,...rows.map(r=>r.value));return rows.map(r=>'<button class="bar-row" '+action(r)+'><span>'+esc(r.label)+'</span><span class="bar-track"><i style="width:'+(r.value/max*100)+'%;background:'+r.color+'"></i></span><b>'+num(r.value)+'</b></button>').join('');}
async function loadLedger(force=false){
 const d=await overview(force);if(!state.ledger||force)state.ledger=await api('/pulse/api/revision/ledger');const l=state.ledger;
 const hotSources=['xiaohongshu','douyin','thepaper','bilibili-hot-search','bilibili-popular','toutiao'],memeSources=['douyin','bilibili-hot-search','bilibili-popular','weibo','baidu'];
 $('ledgerMetrics').innerHTML=metric('累计校内独立帖',l.unique_school_posts)+metric('青年热点来源记录',l.sources.filter(s=>hotSources.includes(s.source)).reduce((n,s)=>n+s.unique,0))+metric('梗文化来源记录',l.sources.filter(s=>memeSources.includes(s.source)).reduce((n,s)=>n+s.unique,0))+metric('已完成研究报告',l.reports_completed);
 const themeRows=d.themes.map(t=>({label:t.theme,value:t.posts,color:t.color})),sourceRows=l.sources.map((s,i)=>({label:NAMES[s.source]||s.source,key:s.source,value:s.unique,color:d.themes[i%d.themes.length].color}));
 const emotions=['积极','中性','消极'].map((label,i)=>({label,value:d.emotion[label]||0,color:['#5fb98f','#a9b8cc','#f28f6b'][i]}));
 $('ledgerDonuts').innerHTML=donut('校内议题分布 · 十日',themeRows,d.total,r=>'data-theme-trend="'+esc(r.label)+'"')+donut('文本表达倾向 · 七日',emotions,emotions.reduce((n,x)=>n+x.value,0),r=>'data-emotion="'+r.label+'"')+donut('累计采集来源',sourceRows,l.unique_items,r=>'data-source="'+r.key+'"','条');
 $('themeBars').innerHTML=bars(themeRows,r=>'data-theme-trend="'+esc(r.label)+'"');$('sourceBars').innerHTML=bars(sourceRows,r=>'data-source="'+r.key+'"');
 if(!l.daily_usage){$('tokenChart').innerHTML='';return;}
 const total=l.daily_usage.reduce((n,x)=>n+(x.tokens||0),0),unknown=l.daily_usage.reduce((n,x)=>n+(x.unknown_calls||0),0);
 $('tokenChart').innerHTML='<div class="usage-summary"><div><span>近14天已记录用量</span><strong>'+num(total)+' <small>Token</small></strong></div><p>'+l.daily_usage.length+' 天 · 含今天'+(unknown?' · '+num(unknown)+' 次调用未返回用量':'')+'</p></div><div class="usage-days">'+l.daily_usage.map(x=>'<article class="usage-day"><time>'+esc(x.day)+'</time><strong>'+(x.has_records===false?'—':num(x.tokens))+'</strong><span>Token</span>'+(x.unknown_calls?'<small>'+num(x.unknown_calls)+' 次调用未提供用量</small>':(x.has_records===false?'<small>当日暂无记录</small>':'<small>当日已记录</small>'))+'</article>').join('')+'</div>'+(l.daily_usage.length?'':'<p class="empty">开始研究后，这里会留下每天的用量记录。</p>');
}
async function openSource(source){if(['huyou-school','tieba-school','xiaohongshu-school','douyin-school'].includes(source))return openPosts({source},NAMES[source]+' · 原帖');const version=showDialog((NAMES[source]||source)+' · 采集记录');try{const d=await api('/pulse/api/revision/source-posts?'+qs({source}));if(version===state.modalVersion)$('detailBody').innerHTML='<p class="muted">近7天 '+num(d.total)+' 条独立记录</p>'+renderPosts(d.posts);}catch(e){if(version===state.modalVersion)$('detailBody').innerHTML=errorState(e.message);}}
const METHODS={sample:['采集范围','校内讨论来自狐友华理圈、华理贴吧，以及公开搜索索引收录的小红书和抖音华理讨论；索引摘要不代表平台完整正文或全量讨论。首页显示近7天，趋势显示近10天。帖子按来源与帖子标识合并，同一帖多次采集合并计数；各平台分别计数。'],emotion:['文本表达倾向','使用固定词典 lexicon-1 统计积极与消极词出现次数，前三字内否定词反转。积极命中数高于消极记为积极，低于记为消极，相等记为中性；比例按帖子数计算。此项描述采集文本，词典与规则可复查。'],heat:['来源内互动分位','狐友互动原始量 = ln(1+累计曝光)+2ln(1+累计回复)，贴吧 = 2ln(1+累计回复)。在同来源样本中计算百分位，零互动记为0，同互动量同分。曝光单位为展示次数。'],trend:['新增帖与次日参考','每24小时按帖子发布时间统计独立新帖，缺少发布时间时采用首次采集时间。相邻两个完整日窗计算增量；缺测保留空值。次日参考取最近十日完整日窗的算术平均值并四舍五入为整数篇，至少3个完整日窗才提供。历史误差通过逐窗回看、只使用此前资料计算平均绝对误差。'],signal:['升温信号','排名权重 w=1/log₂(排名+1)。取同平台此前24小时各采集批次的权重序列，未上榜记为0；S=(当前权重−历史均值)/√(历史方差+0.05)。至少3次历史观测，按S降序排列，信号相同按采集记录的来源序位排序。该指标由排名记录计算。']};
function showMethod(key){const m=METHODS[key]||METHODS.sample;const dialog=document.createElement('dialog');dialog.className='config-dialog';dialog.innerHTML='<div class="dialog-head"><h2>'+esc(m[0])+'</h2><button aria-label="关闭">×</button></div><div class="dialog-body method-text"><p>'+esc(m[1])+'</p></div>';document.body.append(dialog);dialog.querySelector('button').onclick=()=>dialog.close();dialog.addEventListener('close',()=>dialog.remove());dialog.showModal();}
async function loadReports(){try{const d=await api('/pulse/api/revision/research');$('researchHistory').innerHTML=d.items.map(t=>'<article class="record"><div><strong>'+esc(t.query)+'</strong><p>'+date(t.created_at)+' · '+esc(({completed:'已完成',running:'研究中',reporting:'报告汇总中',awaiting_report:'待生成报告',queued:'排队中',failed:'未完成'})[t.status]||t.status)+'</p></div><div class="record-actions">'+(t.status==='completed'?'<button data-report="'+esc(t.task_id)+'">阅读报告 ↗</button><a href="/pulse/api/revision/research/'+encodeURIComponent(t.task_id)+'/report?format=pdf" target="_blank" rel="noopener">导出 PDF</a>':(t.status==='awaiting_report'||t.can_resume_report)?'<button data-resume-report="'+esc(t.task_id)+'">继续生成报告 ↗</button>':t.status!=='failed'?'<button data-resume="'+esc(t.task_id)+'">查看进度</button>':'<button data-repeat-query="'+esc(t.query)+'">重新研究 ↗</button>')+'</div></article>').join('')||empty('生成的研究报告将在这里归档');}catch(e){$('researchHistory').innerHTML=errorState(e.message,'research');}}
function openReport(task){const version=showDialog('事件分析报告');$('detailBody').innerHTML='<p class="muted">事件分析 · A4 自然分页 <a href="/pulse/api/revision/research/'+encodeURIComponent(task)+'/report?format=pdf" target="_blank" rel="noopener">下载 PDF ↗</a></p><iframe title="事件分析报告" sandbox="allow-scripts allow-popups" style="width:100%;height:65dvh;border:0;margin-top:15px" src="/pulse/api/revision/research/'+encodeURIComponent(task)+'/report"></iframe>';return version;}
async function pollTask(task){
 clearTimeout(state.poll);state.task=task;$('researchProgress').hidden=false;$('researchSubmit').disabled=true;
 try{const d=await api('/pulse/api/revision/research/'+encodeURIComponent(task));if(state.task!==task)return;
  const names={query:'查询取证',media:'媒体检索',insight:'公众讨论分析'},labels={idle:'准备中',queued:'排队中',running:'进行中',completed:'已完成',failed:'未完成'};
  $('researchProgress').innerHTML='<strong>'+esc(d.status==='reporting'?'资料已汇集，正在生成事件报告':d.status==='awaiting_report'?'研究材料已齐备，等待生成报告':d.status==='completed'?'报告已生成':d.status==='failed'?'研究未完成':'正在开展事件研究')+'</strong><div class="engine-status">'+Object.entries(d.engines).map(([e,s])=>'<span>'+esc(names[e]||e)+' · '+esc(labels[s]||s)+'</span>').join('')+'</div>'+(d.error?'<p class="error">'+esc(d.error)+'</p>':'')+((d.status==='awaiting_report'||d.can_resume_report)?'<p><button data-resume-report="'+esc(task)+'">继续生成报告 ↗</button></p>':'')+(d.status==='completed'?'<p><button data-report="'+esc(task)+'">阅读报告 ↗</button></p>':'');
  if(['completed','failed'].includes(d.status)){$('researchForm').hidden=false;$('researchSubmit').disabled=false;state.lastSubmittedQuery=null;state.requestId=null;localStorage.removeItem('ecust-active-research-v2');if(d.status==='failed'&&activeBrief){$('researchBrief').hidden=false;showResearchStep(true);}else{activeBrief=null;showResearchStep(false);}updateResearchAction();await loadReports();}
  else state.poll=setTimeout(()=>pollTask(task),4000);
 }catch(e){$('researchProgress').innerHTML=errorState(e.message)+'<button data-resume="'+esc(task)+'">继续查看进度</button>';$('researchSubmit').disabled=false;}
}
let briefVersion=0,briefTimer,activeBrief=null,briefBusy=false;
function briefFeedback(message,error=false){const el=$('briefFeedback');el.hidden=!message;el.textContent=message;el.classList.toggle('error',error);}
function updateResearchAction(){
 const ready=activeBrief&&['ready','failed'].includes(activeBrief.status);
 $('researchSubmit').textContent=briefBusy?'正在找线索…':ready?'开始研究 ↗':'查找线索 ↗';
}
function briefBusyState(busy){briefBusy=busy;$('researchSubmit').disabled=busy;updateResearchAction();}
function showResearchStep(confirm){$('researchEntry').hidden=confirm;$('researchTopicSummary').hidden=!confirm;$('researchTopicText').textContent=$('researchQuery').value;$('researchTopicText').title=$('researchQuery').value;}
function resetBrief(){const researchRunning=!briefBusy&&$('researchSubmit').disabled&&state.task;briefVersion++;clearTimeout(briefTimer);activeBrief=null;briefBusyState(false);if(researchRunning)$('researchSubmit').disabled=true;briefFeedback('');$('researchBrief').hidden=true;showResearchStep(false);localStorage.removeItem('ecust-research-brief-v1');}
$('researchQuery').addEventListener('input',resetBrief);
$('researchEditTopic').onclick=e=>{e.preventDefault();if($('researchSubmit').disabled)return;const focus=$('researchFocus')?.value.trim();if(focus)$('researchQuery').value=focus;resetBrief();$('researchQuery').focus();};
async function researchAction(){
 if(briefBusy||$('researchSubmit').disabled)return;
 if(!activeBrief||!['ready','failed'].includes(activeBrief.status))return submitResearchBrief();
 return launchResearch();
}
$('researchSubmit').onclick=researchAction;
function renderBrief(d){
 activeBrief=d;const host=$('researchBrief');host.hidden=false;
 if(d.status==='preparing'){showResearchStep(true);host.innerHTML='<p class="brief-loading"><span class="brief-dot" aria-hidden="true"></span>正在寻找相关线索…</p>';return;}
 const directions=d.directions||[],original=d.query||$('researchQuery').value;showResearchStep(true);briefBusyState(false);briefFeedback('');
 const choices=directions.map((item,i)=>({...item,key:String(i),kind:'检索线索'}));
 if(!choices.length)choices.push(
  {key:'pending-event',kind:'待确认切入点',title:'先确认你指的事件与对象',query:original,reason:d.question||d.interpretation_note||'先明确这句话指哪件事、涉及谁，再核对背景与经过。'},
  {key:'pending-discussion',kind:'待确认切入点',title:'看看大家在讨论什么',query:original+'：重点梳理讨论焦点、不同观点与传播过程。',reason:'围绕原话查找讨论材料，具体指代仍需核实。'});
 choices.push({key:'custom',kind:'自定义',title:'都不太对，我来说明',query:original,reason:'写下你指的具体事情，以及想重点研究的问题。'});
 host.innerHTML='<fieldset class="brief-options"><legend>选一个关注方向</legend>'+choices.map((item,i)=>'<label class="brief-option"><input type="radio" name="briefDirection" value="'+esc(item.key)+'" '+(i===0?'checked':'')+'><span><strong>'+esc(item.title)+' <em class="brief-choice-kind">'+esc(item.kind)+'</em></strong><span>'+esc(item.reason)+'</span>'+(item.citations||[]).slice(0,1).map(c=>{const source=(d.sources||[]).find(x=>x.id===c.id);return source?'<small>线索：'+(safeUrl(source.url)?'<a href="'+esc(safeUrl(source.url))+'" target="_blank" rel="noopener noreferrer" title="'+esc(c.quote)+'">'+esc(source.title)+' ↗</a>':esc(source.title))+'</small>':'';}).join('')+'</span></label>').join('')+'</fieldset><label id="researchFocusLabel" for="researchFocus">你的研究问题</label><textarea id="researchFocus" rows="4" maxlength="500" placeholder="说明你指的对象或事件、时间、相关人物，以及想重点研究什么；有链接也可以贴入。"></textarea>';
 const drafts=Object.fromEntries(choices.map(item=>[item.key,item.query+(d.context&&!item.query.includes(d.context)?'\n'+d.context:'')]));let choice=choices[0].key;
 try{const saved=JSON.parse(localStorage.getItem('ecust-research-brief-v1')||'null');if(saved?.id===d.id){if(saved.drafts&&typeof saved.drafts==='object')for(const item of choices)if(typeof saved.drafts[item.key]==='string')drafts[item.key]=saved.drafts[item.key];if(typeof saved.focus==='string'){choice=choices.some(item=>item.key===saved.choice)?saved.choice:'custom';drafts[choice]=saved.focus;}}}catch{}
 function select(key){choice=key;host.querySelectorAll('input[name="briefDirection"]').forEach(r=>r.checked=r.value===key);$('researchFocus').value=drafts[key];$('researchFocusLabel').textContent=key==='custom'?'自定义研究问题':'你的研究问题';}
 function persist(){try{const saved=JSON.parse(localStorage.getItem('ecust-research-brief-v1')||'null');if(saved&&saved.id===d.id){Object.assign(saved,{focus:$('researchFocus').value,choice,drafts});localStorage.setItem('ecust-research-brief-v1',JSON.stringify(saved));}}catch{}}
 select(choice);
 host.querySelectorAll('input[name="briefDirection"]').forEach(r=>r.addEventListener('change',()=>{drafts[choice]=$('researchFocus').value;select(r.value);persist();}));
 $('researchFocus').addEventListener('input',()=>{const value=$('researchFocus').value;choice='custom';drafts.custom=value;host.querySelector('input[value="custom"]').checked=true;$('researchFocusLabel').textContent='自定义研究问题';persist();});
 $('researchFocus').focus({preventScroll:true});$('researchTopicSummary').scrollIntoView({block:'nearest',behavior:'auto'});
}
async function launchResearch(){
 const d=activeBrief,query=$('researchFocus').value.trim(),context='';
 if(!query||Array.from(query).length>500){briefFeedback('研究问题请输入1至500字',true);$('researchFocus').focus();return;}
 if(Array.from(context).length>500){briefFeedback('补充信息请控制在500字以内',true);return;}
 const selected=$('researchBrief').querySelector('input[name="briefDirection"]:checked');
 const direction=selected&&/^\d+$/.test(selected.value)?Number(selected.value):null;
 const key=JSON.stringify([d.id,direction,query,context]);
 if(state.lastSubmittedQuery!==key){state.requestId=crypto.randomUUID();state.lastSubmittedQuery=key;}
 briefFeedback('');$('researchSubmit').disabled=true;$('researchSubmit').textContent='正在发起研究…';
 try{const task=await api('/pulse/api/revision/research',{method:'POST',body:JSON.stringify({query,brief_id:d.id,direction,context,exploratory:true,request_id:state.requestId})});localStorage.removeItem('ecust-research-brief-v1');$('researchBrief').hidden=true;showResearchStep(false);localStorage.setItem('ecust-active-research-v2',task.task_id);$('researchForm').hidden=true;pollTask(task.task_id);}
 catch(error){briefFeedback(error.message,true);$('researchSubmit').disabled=false;updateResearchAction();}
}
async function pollBrief(id,version){
 try{const d=await api('/pulse/api/revision/research/brief/'+encodeURIComponent(id));if(version!==briefVersion)return;renderBrief(d);if(d.status==='preparing')briefTimer=setTimeout(()=>pollBrief(id,version),2000);}
 catch(error){if(version!==briefVersion)return;let draft=$('researchQuery').value;try{const saved=JSON.parse(localStorage.getItem('ecust-research-brief-v1')||'null');if(saved?.id===id)draft=saved.focus||[saved.query,saved.context].filter(Boolean).join('\n');}catch{}renderBrief({status:'failed',query:draft,context:'',directions:[],id:null,question:'暂时没取到线索，可以在这里写下具体想了解的问题。'});briefFeedback(error.message,true);}
}
async function submitResearchBrief(){
 if(briefBusy||$('researchSubmit').disabled)return;
 const query=$('researchQuery').value.trim(),context=activeBrief?.context||'';
 if(!query||Array.from(query).length>500){briefFeedback('请输入1至500字的研究主题',true);$('researchQuery').focus();return;}
 const previousBrief=activeBrief;const version=++briefVersion;clearTimeout(briefTimer);briefBusyState(true);briefFeedback('');renderBrief({status:'preparing'});

 try{const d=await api('/pulse/api/revision/research/brief',{method:'POST',body:JSON.stringify({query,context})});if(version!==briefVersion)return;localStorage.setItem('ecust-research-brief-v1',JSON.stringify({id:d.id,query,context}));renderBrief(d);if(d.status==='preparing')pollBrief(d.id,version);}
 catch(error){if(version!==briefVersion)return;renderBrief(previousBrief&&['ready','failed'].includes(previousBrief.status)?{...previousBrief,context}:{status:'failed',query,context,directions:[],id:null});briefFeedback(error.message+'；可以按当前问题开始研究。',true);}
}
$('researchForm').addEventListener('submit',e=>{e.preventDefault();researchAction();});

try{const saved=JSON.parse(localStorage.getItem('ecust-research-brief-v1')||'null');if(saved&&!localStorage.getItem('ecust-active-research-v2')){$('researchQuery').value=saved.query;$('researchSubmit').disabled=true;pollBrief(saved.id,++briefVersion);}}catch{}

$('collectButton').onclick=async()=>{const b=$('collectButton');b.disabled=true;try{await api('/pulse/api/collect',{method:'POST',body:'{}'});notice('采集任务已提交，完成后可刷新页面查看。');}catch(e){notice(e.message);}finally{b.disabled=false;}};
let service='llm',serviceConfig=null,serviceDraft={};
function stashService(){if(service==='llm'||service==='search')Object.assign(serviceDraft,Object.fromEntries(new FormData($('configForm')).entries()));}
async function config(tab='llm'){
 try{
  stashService();service=tab;
  document.querySelectorAll('[data-service]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.service===tab)));
  $('configForm').hidden=tab==='mail'||tab==='accounts';$('mailSettingsPane').hidden=tab!=='mail';$('accountsPane').hidden=tab!=='accounts';$('configStatus').textContent='';
  if(!$('configDialog').open)$('configDialog').showModal();
  if(tab==='mail'){await window.CampusWeekly.fill();return;}
  if(tab==='accounts'){await window.CampusAccounts.fill();return;}
  if(!serviceConfig){const d=await api('/api/config');serviceConfig=d.config;}
  const c={...serviceConfig,...serviceDraft};
  $('serviceIntro').textContent=tab==='llm'?'五个研究环节可分别选择模型。密钥留空时沿用已保存值。':'博查为事件研究和新梗核对提供网页资料。密钥留空时沿用已保存值。';
  const engines=[['QUERY','查询模型','查找事件材料'],['MEDIA','媒体模型','分析媒体内容'],['INSIGHT','洞察模型','分析讨论材料'],['REPORT','报告模型','事件报告、校园周报与新梗发现'],['FORUM_HOST','讨论汇总模型','整合研究观点']];
  $('configFields').innerHTML=tab==='search'?'<section class="config-engine"><h3>博查 Bocha</h3><label>检索密钥<input name="BOCHA_WEB_SEARCH_API_KEY" type="password" autocomplete="off" placeholder="'+(serviceConfig.BOCHA_WEB_SEARCH_API_KEY?'已配置，留空沿用':'填写博查 API Key')+'"></label></section>':engines.map(([id,label,role],i)=>{const prefix=id==='FORUM_HOST'?id:id+'_ENGINE';return '<details class="config-engine" '+(i===3?'open':'')+'><summary><strong>'+label+'</strong><span>'+role+'</span></summary>'+[['BASE_URL','接口地址'],['MODEL_NAME','模型名称'],['API_KEY','密钥']].map(([suffix,name])=>{const key=prefix+'_'+suffix;return '<label>'+name+'<input name="'+key+'" type="'+(suffix==='API_KEY'?'password':'text')+'" value="'+esc(suffix==='API_KEY'?(serviceDraft[key]||''):(c[key]||''))+'" autocomplete="off" placeholder="'+(suffix==='API_KEY'?(serviceConfig[key]?'已配置，留空沿用':'填写 API Key'):'')+'"></label>';}).join('')+'</details>';}).join('');
  if(tab==='search')$('configForm').elements.BOCHA_WEB_SEARCH_API_KEY.value=serviceDraft.BOCHA_WEB_SEARCH_API_KEY||'';
 }catch(e){notice(e.message);}
}
window.CampusSettings={open:config};
$('configButton').onclick=()=>config('llm');
document.querySelectorAll('[data-service]').forEach(b=>b.onclick=()=>config(b.dataset.service));
$('configForm').onsubmit=async e=>{e.preventDefault();const updates=Object.fromEntries(Object.entries(Object.fromEntries(new FormData(e.target).entries())).filter(([k,v])=>!k.endsWith('API_KEY')||v.trim()));const b=e.target.querySelector('button.primary');b.disabled=true;try{const d=await api('/api/config',{method:'POST',body:JSON.stringify(updates)});serviceConfig=d.config;for(const key of Object.keys(updates))delete serviceDraft[key];e.target.querySelectorAll('input[type=password]').forEach(x=>x.value='');$('configStatus').textContent='当前服务配置已保存';}catch(error){$('configStatus').textContent=error.message;}finally{b.disabled=false;}};
document.addEventListener('click',e=>{
 const b=e.target.closest('button,[role="button"]');if(!b)return;
 if(b.classList.contains('close-dialog')){b.closest('dialog').close();return;}
 if(b.dataset.tab)return activate(b.dataset.tab);
 if(b.dataset.theme)return openPosts({theme:b.dataset.theme,from:state.overview.generated_at-7*DAY},b.dataset.theme+' · 原帖');
 if(b.dataset.themeTrend)return openTrend(b.dataset.themeTrend);
 if(b.dataset.word)return openPosts({word:b.dataset.word},'关键词 · '+b.dataset.word);
 if(b.dataset.emotion)return openPosts({emotion:b.dataset.emotion,from:state.overview.generated_at-7*DAY},b.dataset.emotion+'表达 · 原帖');
 if(b.dataset.source)return openSource(b.dataset.source);
 if(b.dataset.method)return showMethod(b.dataset.method);
 if(b.dataset.feed){if(b.dataset.feed==='hot')state.hotPlatform=b.dataset.platform;return loadFeed(b.dataset.feed).catch(x=>notice(x.message));}
 if(b.dataset.retry){if(b.dataset.retry==='campus'||b.dataset.retry==='trends')state.overview=null;return activate(b.dataset.retry);}
 if(b.dataset.report)return openReport(b.dataset.report);
 if(b.dataset.resumeReport){b.disabled=true;api('/pulse/api/revision/research/'+encodeURIComponent(b.dataset.resumeReport)+'/resume-report',{method:'POST',body:'{}'}).then(()=>{localStorage.setItem('ecust-active-research-v2',b.dataset.resumeReport);pollTask(b.dataset.resumeReport);loadReports();}).catch(error=>{b.disabled=false;notice(error.message);});return;}
 if(b.dataset.resume)return pollTask(b.dataset.resume);
 if(b.dataset.repeatQuery){$('researchQuery').value=b.dataset.repeatQuery;$('researchQuery').dispatchEvent(new Event('input'));state.lastSubmittedQuery=null;state.requestId=null;activate('research');$('researchQuery').focus();return;}
});
document.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)&&e.target.matches('[role="button"]')&&!e.target.matches('button')){e.preventDefault();e.target.dispatchEvent(new MouseEvent('click',{bubbles:true}));}});
$('detailDialog').addEventListener('close',()=>state.modalVersion++);
setInterval(async()=>{
 if(document.hidden||state.overviewPromise)return;
 try{if(['campus','trends'].includes(state.tab)){await overview(true);renderCampus();renderTrends();}
 else if(['hot','memes'].includes(state.tab))await loadFeed(state.tab,true);
 }catch{/* Keep the last successful view and its displayed timestamp. */}
},120000);
$('practicePosts').onclick=async()=>{try{const data=await overview();openPosts({red:'1',from:data.generated_at-7*DAY},'红色育人观察 · 实践原帖');}catch(e){notice(e.message);}};$('carePosts').onclick=openCare;
$('refreshReports').onclick=loadReports;$('refreshLedger').onclick=()=>loadLedger(true).catch(e=>notice(e.message));
activate(location.hash.slice(1)||'campus');loadCare();try{const active=localStorage.getItem('ecust-active-research-v2');if(active)pollTask(active);}catch{}
})();
