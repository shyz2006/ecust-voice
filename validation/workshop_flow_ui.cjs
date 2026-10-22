const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('assert');
const root=path.resolve(__dirname,'../production'),out=path.resolve(__dirname,'../../validation-artifacts/workshop-flow');fs.mkdirSync(out,{recursive:true});
const names=['学业课程','考试考证','升学就业','校园设施与管理','食堂与生活服务','宿舍生活','社交与同伴','恋爱情感','身心与情绪','文体与实践','交易与互助','其他校园讨论'];
const colors=['#527a99','#8278a6','#547d70','#ba8954','#bf8173','#95816f','#6f91a0','#b97b97','#7b9770','#aa9158','#819398','#96958f'];
const now=1792454400,DAY=86400;
const themes=names.map((theme,i)=>({theme,color:colors[i],posts:30+i,posts_7d:20+i,posts_24h:4+i,delta:i%3===0?null:i-5,examples:Array.from({length:3},(_,n)=>({content:'这里是界面验证示例，展示同学对具体校园问题的讨论。'+n,link:'https://example.com/latest/'+n})),reference:{value:4.5,windows:8,mae:1.2,validation_windows:4,method:'最近十日完整24小时窗口的新增帖数算术平均值'},timeline:Array.from({length:10},(_,d)=>({ts:now-(10-d)*DAY,posts:d+i,new_posts:d===3?null:d+i,observed:d!==3}))}));
const overview={success:true,generated_at:now,window_start:now-10*DAY,window_days:10,taxonomy:names,themes,total:426,total_7d:306,emotion:{积极:25,中性:250,消极:31},practice_count:7,coverage:themes[0].timeline.map(p=>({ready:p.observed})),wordcloud:['图书馆','课程','食堂','宿舍','选课','实习','志愿服务','运动','论文','校区','网络','社团','考试','实验室','学习'].map((term,i)=>({term,df:50-i*3}))};
const posts=Array.from({length:15},(_,i)=>({id:String(i),source:i%2?'tieba-school':'huyou-school',theme:names[i%12],content:'验证用示例正文。'.repeat(35),published:now-i*1000,emotion:'中性',heat:70,link:'https://example.com/post/'+i}));
let briefSubmissions=[],submitted=[],weeklySubmissions=[],serviceSubmissions=[],failResearch=false,failBrief=false,failTask=false;
const server=http.createServer((req,res)=>{
 const url=new URL(req.url,'http://localhost'),p=url.pathname;
 const json=(data,status=200)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify(data));};
 if(p==='/pulse/api/revision/overview')return json(overview);
 if(p==='/pulse/api/campus')return json({success:true,voice:{crisis:{高危:1,关注:2}}});
 if(p==='/pulse/api/campus/crisis-posts')return json({success:true,posts:posts.slice(0,3),total:3,filtered_posts:posts.slice(3,5),filtered_total:2});
 if(p==='/pulse/api/revision/posts'||p==='/pulse/api/revision/source-posts')return json({success:true,posts,total:posts.length});
 if(p==='/pulse/api/revision/feed/hot')return json({success:true,platforms:['抖音','澎湃','B站','头条'],method:'formula',items:['抖音','澎湃','B站','头条'].flatMap(platform=>Array.from({length:15},(_,i)=>({platform,id:i,title:platform+'热点阅读测试'+i,rank:i+1,ts:now,signal:15-i,url:'https://example.com/hot/'+i,focus:'这是已采集报道的关注焦点摘要。'})))});
 if(p==='/pulse/api/revision/feed/memes')return json({success:true,platforms:[],message:'本轮发现与核对完成',running:false,generated_at:now,candidates:Array.from({length:6},(_,i)=>({term:'示例新表达'+i,form:'模仿句式',observation:'用例中的说法以夸张的比喻表达开心，便于朋友之间模仿和接梗。',observed_count:1,reason:'等待更多独立内容使用该表达',links:[{platform:'B站',title:'真实用例标题'+i,url:'https://www.bilibili.com/video/BV122nu6sEKG/'}]})),items:Array.from({length:4},(_,i)=>({term:'流行表达 '+i,form:'网络流行语',meaning:'流行表达释义验证。',usage:'一般大学生活中的表达场景。',examples:['这是一句表达示例。'],evidence_status:'近期采集用例',reference_url:'https://example.com/meaning/'+i,reference_title:'释义参考',search_links:[{platform:'B站',url:'https://example.com/search/'+i}],links:[{platform:'B站',url:'https://example.com/meme/'+i,title:'实际采集的标题'}]}))});
 if(p==='/pulse/api/revision/ledger')return json({success:true,unique_school_posts:4000,reports_completed:31,unique_items:17000,sources:Object.keys({'douyin':1,'thepaper':1,'bilibili-popular':1,'bilibili-hot-search':1,'toutiao':1,'weibo':1,'baidu':1,'huyou-school':1,'tieba-school':1}).map((source,i)=>({source,unique:1000+i*200})),daily_usage:Array.from({length:14},(_,i)=>({day:'2026-10-'+String(i+7),has_records:i>0,tokens:i?i*13000:null,unknown_calls:i===2?1:0}))});
 if(p==='/pulse/api/revision/weekly/config'&&req.method==='POST'){let body='';req.on('data',x=>body+=x);req.on('end',()=>{weeklySubmissions.push(JSON.parse(body));json({success:true});});return;}
 if(p==='/pulse/api/revision/weekly/config')return json({success:true,config:{enabled:false,sender:'',recipients:[],key_configured:true,sender_verified:true,weekday:4,send_time:'14:00',lead_minutes:30,schedule:'每周五 14:00发送，当天13:30截稿生成 · 北京时间',next_send:now+86400}});
 if(p==='/pulse/api/revision/weekly')return json({success:true,items:[{id:'preview_fixture',kind:'preview',cutoff:now,created:now,status:'ready',send_state:'pending'}],config:{enabled:false,sender:'',recipients:[],key_configured:true,sender_verified:true,weekday:4,send_time:'14:00',lead_minutes:30,schedule:'每周五 14:00发送，当天13:30截稿生成 · 北京时间',next_send:now+86400}});
 if(p==='/pulse/api/revision/research/brief'&&req.method==='POST'){
  let body='';req.on('data',x=>body+=x);req.on('end',()=>{const b=JSON.parse(body);briefSubmissions.push(b);if(failBrief)return json({success:false,message:'测试：搜索服务暂时不可用，请重试'},503);json({success:true,id:'a'.repeat(32),query:b.query,context:b.context,status:'ready',interpretation_note:'“内战”是指网络上的学科争论吗？请核对下面的方向。',sources:[{id:'S1',title:'校园学科争论的资料线索',url:'https://example.com/source'}],directions:b.query==='资料不足'?[]:[{title:'文理学科身份与网络争论',query:'武汉大学文科与理工科的学科争论如何产生和传播？',reason:'把内战作为网络比喻，核对不同观点。',citations:[{id:'S1',quote:'武汉大学部分网络讨论围绕文科与理工科争论展开'}]}],question:'可以补充讨论的时间或相关原帖吗？'});});return;
 }
 if(p==='/pulse/api/revision/research'&&req.method==='POST'){
  let body='';req.on('data',x=>body+=x);req.on('end',()=>{submitted.push(JSON.parse(body));json(failResearch?{success:false,message:'研究服务启动失败'}:{success:true,task_id:'task_fixture'},failResearch?503:200);});return;
 }
 if(p==='/pulse/api/revision/research')return json({success:true,items:[{task_id:'task_fixture',query:'校园信息公开事件研究',created_at:now,status:'completed'}]});
 if(p==='/pulse/api/revision/research/task_fixture')return json({success:true,status:failTask?'failed':'completed',error:failTask?'本轮尚未找到能确认对象的原始资料。':'',query:'研究示例',engines:{query:'completed',media:'completed',insight:'completed'}});
 if(p.endsWith('/report')){res.setHeader('Content-Type','text/html');res.end('<!doctype html><html lang="zh"><body>四章事件报告界面验证</body></html>');return;}
 if(p==='/api/config'&&req.method==='POST'){let body='';req.on('data',x=>body+=x);req.on('end',()=>{serviceSubmissions.push(JSON.parse(body));json({success:true,config:{}});});return;}
 if(p==='/api/config')return json({success:true,config:{}});
 const file=p==='/'||p==='/pulse/'?path.join(root,'templates/index.html'):path.join(root,p);
 if(!file.startsWith(root)||!fs.existsSync(file)){res.writeHead(404);res.end();return;}
 res.setHeader('Content-Type',file.endsWith('.html')?'text/html; charset=utf-8':file.endsWith('.css')?'text/css':file.endsWith('.js')?'text/javascript':'application/octet-stream');res.end(fs.readFileSync(file));
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const results=[];
 for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:width===1440?1000:844}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await page.goto('http://127.0.0.1:'+server.address().port+'/#research');
  const action=page.locator('#researchSubmit');
  assert.equal(await page.locator('#researchContext').isVisible(),false);
  assert.equal(await page.locator('#researchForm button.primary').count(),1);
  await page.locator('#researchQuery').fill('资料不足');await action.click();
  await page.locator('#researchFocus').waitFor();assert.equal(await action.textContent(),'开始研究 ↗');
  assert.equal(await page.locator('#researchFocus').inputValue(),'资料不足');
  for(const context of ['背景一','背景一；背景二','背景一；背景二；背景三']){
   await page.locator('#researchContext').fill(context);
   assert(await action.isEnabled());await page.locator('#researchRefreshFirst').check();
   assert.equal(await action.textContent(),'更新线索 ↻');await action.click();
   await page.locator('#researchFocus').waitFor();assert.equal(await action.textContent(),'开始研究 ↗');
   assert.equal(await page.locator('#researchContext').inputValue(),context);
   assert.equal(briefSubmissions.at(-1).context,context);
  }
  const calls=briefSubmissions.length;
  await page.locator('#researchContext').fill('另加用户刚输入的背景，直接带入研究');
  await page.screenshot({path:path.join(out,'empty-directions-'+width+'.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  failResearch=true;await action.click();await page.locator('#briefFeedback.error').waitFor();assert(await action.isEnabled());
  const requestId=submitted.at(-1).request_id;failResearch=false;
  await action.dblclick();await page.locator('#researchProgress [data-report]').waitFor();
  assert.equal(submitted.at(-1).request_id,requestId);assert.equal(submitted.at(-1).direction,null);
  assert.equal(submitted.at(-1).context,'另加用户刚输入的背景，直接带入研究');
  assert.equal(submitted.at(-1).exploratory,true);assert.equal(briefSubmissions.length,calls);
  await page.locator('#researchQuery').fill('武汉大学内战');await action.click();await page.locator('#researchFocus').waitFor();
  assert(await page.locator('.brief-option q').isVisible());
  await page.locator('#researchFocus').fill('用户自行修改的研究问题');
  await page.locator('#researchContext').fill('新的补充内容');
  await action.click();await page.locator('#researchProgress [data-report]').waitFor();assert.equal(submitted.at(-1).query,'用户自行修改的研究问题');
  await page.locator('#researchQuery').fill('搜索服务失败测试');failBrief=true;await action.click();
  await page.locator('#briefFeedback.error').waitFor();assert.equal(await action.textContent(),'开始研究 ↗');
  assert.equal(await page.locator('#researchFocus').inputValue(),'搜索服务失败测试');
  await page.locator('#researchContext').fill('失败后的补充');await page.locator('#researchRefreshFirst').check();
  await action.click();await page.locator('#briefFeedback.error').waitFor();assert.equal(await page.locator('#researchContext').inputValue(),'失败后的补充');
  await action.click();await page.locator('#researchProgress [data-report]').waitFor();assert.equal(submitted.at(-1).brief_id,null);failBrief=false;
  await page.waitForFunction(()=>document.getElementById('researchSubmit').textContent==='查找线索 ↗');
  await page.locator('#researchQuery').fill('资料不足');await action.click();await page.locator('#researchFocus').waitFor();
  failTask=true;await action.click();await page.locator('#researchProgress .error').waitFor();await page.waitForFunction(()=>document.getElementById('researchSubmit').textContent==='开始研究 ↗');
  assert(await page.locator('#researchFocus').isVisible());assert(await page.locator('#researchContext').isVisible());assert.equal(await action.textContent(),'开始研究 ↗');failTask=false;
  await page.emulateMedia({reducedMotion:'reduce'});assert.equal(await page.locator('.lens-bob').evaluate(el=>getComputedStyle(el).animationName),'none');
  assert.deepEqual(errors,[]);results.push({width,single_button:true,three_empty_refinements_launch:true,fresh_context_forwarded:true,edited_scope_launch:true,failed_preparation_launch:true,retry_idempotency:true,no_overflow:true,page_errors:errors});await page.close();
 }
 fs.writeFileSync(path.resolve(__dirname,'workshop-flow-ui-results.json'),JSON.stringify({passed:true,results},null,2)+'\n');
 await browser.close();server.close();console.log(JSON.stringify({passed:true,results}));
})().catch(e=>{console.error(e);process.exit(1)});
