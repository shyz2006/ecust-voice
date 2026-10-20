/* Campus review: six focused modules share one category and evidence model. */
(()=>{'use strict';
const $=id=>document.getElementById(id),esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=value=>value==null?'—':Number(value).toLocaleString('zh-CN'),date=ts=>ts?new Date(ts*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'—';
const shortDate=ts=>new Date(ts*1000).toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric'});
const DAY=86400,NAMES={'huyou-school':'狐友华理圈','tieba-school':'华理贴吧','douyin':'抖音','thepaper':'澎湃','bilibili-hot-search':'B站热搜','bilibili-popular':'B站热门','toutiao':'头条','weibo':'微博','baidu':'百度'};
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
 const words=d.wordcloud.slice(0,35),max=Math.max(1,...words.map(w=>w.df)),colors=['#365e4c','#7e735f','#6c8791','#8d7967','#738166'];
 $('wordcloud').innerHTML=words.map((w,i)=>'<button data-word="'+esc(w.term)+'" style="font-size:'+(13+22*Math.sqrt(w.df/max)).toFixed(1)+'px;color:'+colors[i%colors.length]+'" title="'+esc(w.term)+' · '+w.df+' 篇">'+esc(w.term)+'</button>').join('')||empty('采集后将显示校园关键词');
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
 if(!state[kind]||force)state[kind]=await api('/pulse/api/revision/feed/'+kind);
 const d=state[kind],current=state.hotPlatform;
 if(kind==='memes')renderMemeStatus(d);
 $('hotPlatforms').innerHTML=kind==='hot'?d.platforms.map(p=>'<button data-feed="'+kind+'" data-platform="'+esc(p)+'" aria-selected="'+(p===current)+'">'+esc(p)+'</button>').join(''):'';
 const items=(kind==='hot'?d.items.filter(x=>x.platform===current):d.items).slice(0,10);
 $(kind==='hot'?'hotFeed':'memeFeed').innerHTML=items.map((x,i)=>kind==='hot'?`<article class="feed-card"><div class="feed-meta"><span class="feed-index">${String(i+1).padStart(2,'0')} · ${esc(x.platform)}</span><span>${date(x.ts)}</span></div><h2>${esc(x.title)}</h2><p class="signal-sticker">升温 ${x.signal==null?'积累中':num(x.signal)}</p><div class="hot-focus"><h3>关注焦点</h3><p>${esc(x.focus||('话题要点：'+x.title))}</p></div><div class="feed-links">${sourceLink(x.url,'打开对应话题 ↗')}</div></article>`:
 `<article class="feed-card meme-card"><div class="feed-meta"><span class="meme-status">${esc(x.evidence_status||'常用表达')}</span><span>${esc(x.form)}</span></div><h2>${esc(x.term)}</h2><p>${esc(x.meaning)}</p><h3>用在什么场景</h3><p>${esc(x.usage)}</p>${(x.examples||[]).slice(0,1).map(t=>'<div class="example">试着说：'+esc(t)+'</div>').join('')}<div class="meme-reference">${sourceLink(x.reference_url,'释义参考 · '+(x.reference_title||'查看资料'))}${x.reference_quote?'<blockquote>'+esc(x.reference_quote)+'</blockquote>':''}<small>核对于 '+date(x.verified_at)+' · '+num(x.observed_count)+' 个独立内容用例</small></div>${x.links.length?'<div class="observed-examples"><h3>近期采集用例</h3>'+x.links.map(p=>'<p>'+sourceLink(p.url,(p.platform?p.platform+' · ':'')+p.title+' ↗')+'</p>').join('')+'</div>':''}<div class="feed-links">${(x.search_links||[]).map(p=>sourceLink(p.url,p.platform+'搜索 ↗')).join('')}</div></article>`).join('')||empty(kind==='memes'?'新表达正在发现和核对中，候选可在下方查看。':'这个平台的内容正在整理中。');
}

let memePoll;
function renderMemeStatus(d){
 clearTimeout(memePoll);$('memeStatus').textContent=(d.message||'等待首次发现与核对')+(d.generated_at?' · 最近核对 '+date(d.generated_at):'');$('discoverMemes').disabled=!!d.running;
 const pending=d.candidates||[];$('memeCandidates').querySelector('summary').textContent='发现候选 · '+pending.length+' 条';
 $('memeCandidateList').innerHTML=pending.map(x=>'<article class="feed-card candidate-card"><span class="meme-status">待核对</span><h3>'+esc(x.term)+'</h3><p>'+esc(x.reason)+'</p><small>'+num(x.observed_count)+' 个独立内容用例</small>'+(x.links||[]).slice(0,2).map(p=>'<p>'+sourceLink(p.url,p.title+' ↗')+'</p>').join('')+'</article>').join('')||empty('下一轮从新采集内容中继续发现。');
 if(d.running)memePoll=setTimeout(()=>{if(state.tab==='memes')loadFeed('memes',true).catch(e=>notice(e.message));},5000);
}
$('discoverMemes').onclick=async()=>{const b=$('discoverMemes');b.disabled=true;try{const d=await api('/pulse/api/revision/memes/refresh',{method:'POST',body:'{}'});state.memes=d;await loadFeed('memes');if(!d.started&&!d.running)notice('刚刚检查过，稍后可再次发现新表达。');}catch(e){notice(e.message);b.disabled=false;}};

function donut(title,rows,total,action){
 const radius=46,c=2*Math.PI*radius;let offset=0;const circles=rows.filter(r=>r.value>0).map(r=>{const length=c*r.value/(total||1),result='<circle cx="64" cy="64" r="46" fill="none" stroke="'+r.color+'" stroke-width="14" stroke-dasharray="'+length+' '+(c-length)+'" stroke-dashoffset="'+(-offset)+'" transform="rotate(-90 64 64)" role="button" tabindex="0" '+action(r)+' aria-label="'+esc(r.label)+' '+num(r.value)+'"><title>'+esc(r.label)+' '+num(r.value)+'</title></circle>';offset+=length;return result;});
 return '<section class="donut-card"><h2>'+esc(title)+'</h2><div class="donut-visual"><svg viewBox="0 0 128 128"><circle cx="64" cy="64" r="46" fill="none" stroke="#e7e9e1" stroke-width="14"/>'+circles.join('')+'<text x="64" y="63" text-anchor="middle" font-size="17" fill="#24372e">'+num(total)+'</text><text x="64" y="80" text-anchor="middle" font-size="9" fill="#78877c">点击核查</text></svg><div class="donut-legend">'+rows.map(r=>'<button '+action(r)+'><span><i class="dot" style="background:'+r.color+'"></i>'+esc(r.label)+'</span><b>'+num(r.value)+'</b></button>').join('')+'</div></div></section>';
}
function bars(rows,action){const max=Math.max(1,...rows.map(r=>r.value));return rows.map(r=>'<button class="bar-row" '+action(r)+'><span>'+esc(r.label)+'</span><span class="bar-track"><i style="width:'+(r.value/max*100)+'%;background:'+r.color+'"></i></span><b>'+num(r.value)+'</b></button>').join('');}
async function loadLedger(force=false){
 const d=await overview(force);if(!state.ledger||force)state.ledger=await api('/pulse/api/revision/ledger');const l=state.ledger;
 const hotSources=['douyin','thepaper','bilibili-hot-search','bilibili-popular','toutiao'],memeSources=['douyin','bilibili-hot-search','bilibili-popular','weibo','baidu'];
 $('ledgerMetrics').innerHTML=metric('累计校内独立帖',l.unique_school_posts)+metric('青年热点来源记录',l.sources.filter(s=>hotSources.includes(s.source)).reduce((n,s)=>n+s.unique,0))+metric('梗文化来源记录',l.sources.filter(s=>memeSources.includes(s.source)).reduce((n,s)=>n+s.unique,0))+metric('已完成研究报告',l.reports_completed);
 const themeRows=d.themes.map(t=>({label:t.theme,value:t.posts,color:t.color})),sourceRows=l.sources.map((s,i)=>({label:NAMES[s.source]||s.source,key:s.source,value:s.unique,color:d.themes[i%d.themes.length].color}));
 const emotions=['积极','中性','消极'].map((label,i)=>({label,value:d.emotion[label]||0,color:['#77957e','#94a6b2','#b9836e'][i]}));
 $('ledgerDonuts').innerHTML=donut('校内议题分布 · 十日',themeRows,d.total,r=>'data-theme-trend="'+esc(r.label)+'"')+donut('文本表达倾向 · 七日',emotions,emotions.reduce((n,x)=>n+x.value,0),r=>'data-emotion="'+r.label+'"')+donut('累计采集来源',sourceRows,l.unique_items,r=>'data-source="'+r.key+'"');
 $('themeBars').innerHTML=bars(themeRows,r=>'data-theme-trend="'+esc(r.label)+'"');$('sourceBars').innerHTML=bars(sourceRows,r=>'data-source="'+r.key+'"');
 const total=l.daily_usage.reduce((n,x)=>n+(x.tokens||0),0),unknown=l.daily_usage.reduce((n,x)=>n+(x.unknown_calls||0),0);
 $('tokenChart').innerHTML='<div class="usage-summary"><div><span>近14天已记录用量</span><strong>'+num(total)+' <small>Token</small></strong></div><p>'+l.daily_usage.length+' 天 · 含今天'+(unknown?' · '+num(unknown)+' 次调用未返回用量':'')+'</p></div><div class="usage-days">'+l.daily_usage.map(x=>'<article class="usage-day"><time>'+esc(x.day)+'</time><strong>'+(x.has_records===false?'—':num(x.tokens))+'</strong><span>Token</span>'+(x.unknown_calls?'<small>'+num(x.unknown_calls)+' 次调用未提供用量</small>':(x.has_records===false?'<small>当日暂无记录</small>':'<small>当日已记录</small>'))+'</article>').join('')+'</div>'+(l.daily_usage.length?'':'<p class="empty">开始研究后，这里会留下每天的用量记录。</p>');
}
async function openSource(source){if(['huyou-school','tieba-school'].includes(source))return openPosts({source},NAMES[source]+' · 原帖');const version=showDialog((NAMES[source]||source)+' · 采集记录');try{const d=await api('/pulse/api/revision/source-posts?'+qs({source}));if(version===state.modalVersion)$('detailBody').innerHTML='<p class="muted">近7天 '+num(d.total)+' 条独立记录</p>'+renderPosts(d.posts);}catch(e){if(version===state.modalVersion)$('detailBody').innerHTML=errorState(e.message);}}
const METHODS={sample:['采集范围','校内讨论来自狐友华理圈与华理贴吧。首页显示近7天，趋势显示近10天。帖子按来源与帖子标识合并，同一帖多次采集合并计数；各平台分别计数。'],emotion:['文本表达倾向','使用固定词典 lexicon-1 统计积极与消极词出现次数，前三字内否定词反转。积极命中数高于消极记为积极，低于记为消极，相等记为中性；比例按帖子数计算。此项描述采集文本，词典与规则可复查。'],heat:['来源内互动分位','狐友互动原始量 = ln(1+累计曝光)+2ln(1+累计回复)，贴吧 = 2ln(1+累计回复)。在同来源样本中计算百分位，零互动记为0，同互动量同分。曝光单位为展示次数。'],trend:['新增帖与次日参考','每24小时按帖子发布时间统计独立新帖，缺少发布时间时采用首次采集时间。相邻两个完整日窗计算增量；缺测保留空值。次日参考取最近十日完整日窗的算术平均值并四舍五入为整数篇，至少3个完整日窗才提供。历史误差通过逐窗回看、只使用此前资料计算平均绝对误差。'],signal:['升温信号','排名权重 w=1/log₂(排名+1)。取同平台此前24小时各采集批次的权重序列，未上榜记为0；S=(当前权重−历史均值)/√(历史方差+0.05)。至少3次历史观测，按S降序排列，信号相同按采集记录的来源序位排序。该指标由排名记录计算。']};
function showMethod(key){const m=METHODS[key]||METHODS.sample;const dialog=document.createElement('dialog');dialog.className='config-dialog';dialog.innerHTML='<div class="dialog-head"><h2>'+esc(m[0])+'</h2><button aria-label="关闭">×</button></div><div class="dialog-body method-text"><p>'+esc(m[1])+'</p></div>';document.body.append(dialog);dialog.querySelector('button').onclick=()=>dialog.close();dialog.addEventListener('close',()=>dialog.remove());dialog.showModal();}
async function loadReports(){try{const d=await api('/pulse/api/revision/research');$('researchHistory').innerHTML=d.items.map(t=>'<article class="record"><div><strong>'+esc(t.query)+'</strong><p>'+date(t.created_at)+' · '+esc(({completed:'已完成',running:'研究中',reporting:'报告汇总中',queued:'排队中',failed:'未完成'})[t.status]||t.status)+'</p></div><div class="record-actions">'+(t.status==='completed'?'<button data-report="'+esc(t.task_id)+'">阅读报告 ↗</button><a href="/pulse/api/revision/research/'+encodeURIComponent(t.task_id)+'/report?format=pdf" target="_blank" rel="noopener">导出 PDF</a>':t.status!=='failed'?'<button data-resume="'+esc(t.task_id)+'">查看进度</button>':'<button data-repeat-query="'+esc(t.query)+'">重新研究 ↗</button>')+'</div></article>').join('')||empty('生成的研究报告将在这里归档');}catch(e){$('researchHistory').innerHTML=errorState(e.message,'research');}}
function openReport(task){const version=showDialog('事件分析报告');$('detailBody').innerHTML='<p class="muted">四章分析 · A4 自然分页 <a href="/pulse/api/revision/research/'+encodeURIComponent(task)+'/report?format=pdf" target="_blank" rel="noopener">下载 PDF ↗</a></p><iframe title="事件分析报告" sandbox="allow-scripts allow-popups" style="width:100%;height:65dvh;border:0;margin-top:15px" src="/pulse/api/revision/research/'+encodeURIComponent(task)+'/report"></iframe>';return version;}
async function pollTask(task){
 clearTimeout(state.poll);state.task=task;$('researchProgress').hidden=false;$('researchSubmit').disabled=true;
 try{const d=await api('/pulse/api/revision/research/'+encodeURIComponent(task));if(state.task!==task)return;
  const names={query:'查询取证',media:'媒体检索',insight:'公众讨论分析'},labels={idle:'准备中',queued:'排队中',running:'进行中',completed:'已完成',failed:'未完成'};
  $('researchProgress').innerHTML='<strong>'+esc(d.status==='reporting'?'资料已汇集，正在生成事件报告':d.status==='completed'?'报告已生成':d.status==='failed'?'研究未完成':'正在开展事件研究')+'</strong><div class="engine-status">'+Object.entries(d.engines).map(([e,s])=>'<span>'+esc(names[e]||e)+' · '+esc(labels[s]||s)+'</span>').join('')+'</div>'+(d.error?'<p class="error">'+esc(d.error)+'</p>':'')+(d.status==='completed'?'<p><button data-report="'+esc(task)+'">阅读报告 ↗</button></p>':'');
  if(['completed','failed'].includes(d.status)){$('researchSubmit').disabled=false;state.lastSubmittedQuery=null;state.requestId=null;localStorage.removeItem('ecust-active-research-v2');await loadReports();}
  else state.poll=setTimeout(()=>pollTask(task),4000);
 }catch(e){$('researchProgress').innerHTML=errorState(e.message)+'<button data-resume="'+esc(task)+'">继续查看进度</button>';$('researchSubmit').disabled=false;}
}
$('researchForm').addEventListener('submit',async e=>{e.preventDefault();if($('researchSubmit').disabled)return;const query=$('researchQuery').value.trim();if(!query||Array.from(query).length>500){notice('请输入1至500字的研究主题');return;}if(state.lastSubmittedQuery!==query){state.requestId=crypto.randomUUID();state.lastSubmittedQuery=query;}$('researchSubmit').disabled=true;try{const d=await api('/pulse/api/revision/research',{method:'POST',body:JSON.stringify({query,request_id:state.requestId})});localStorage.setItem('ecust-active-research-v2',d.task_id);pollTask(d.task_id);}catch(error){notice(error.message);$('researchSubmit').disabled=false;}});
$('collectButton').onclick=async()=>{const b=$('collectButton');b.disabled=true;try{await api('/pulse/api/collect',{method:'POST',body:'{}'});notice('采集任务已提交，完成后可刷新页面查看。');}catch(e){notice(e.message);}finally{b.disabled=false;}};
let service='llm',serviceConfig=null,serviceDraft={};
function stashService(){if(service!=='mail')Object.assign(serviceDraft,Object.fromEntries(new FormData($('configForm')).entries()));}
async function config(tab='llm'){
 try{
  stashService();service=tab;
  document.querySelectorAll('[data-service]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.service===tab)));
  $('configForm').hidden=tab==='mail';$('mailSettingsPane').hidden=tab!=='mail';$('configStatus').textContent='';
  if(!$('configDialog').open)$('configDialog').showModal();
  if(tab==='mail'){await window.CampusWeekly.fill();return;}
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
