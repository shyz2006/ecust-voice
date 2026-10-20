const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('assert');
const root=path.resolve(__dirname,'../production'),out=path.resolve(__dirname,'../../validation-artifacts/campus-v5');fs.mkdirSync(out,{recursive:true});
const names=['学业课程','考试考证','升学就业','校园设施与管理','食堂与生活服务','宿舍生活','社交与同伴','恋爱情感','身心与情绪','文体与实践','交易与互助','其他校园讨论'];
const colors=['#527a99','#8278a6','#547d70','#ba8954','#bf8173','#95816f','#6f91a0','#b97b97','#7b9770','#aa9158','#819398','#96958f'];
const now=1792454400,DAY=86400;
const themes=names.map((theme,i)=>({theme,color:colors[i],posts:30+i,posts_7d:20+i,posts_24h:4+i,delta:i%3===0?null:i-5,examples:Array.from({length:3},(_,n)=>({content:'这里是界面验证示例，展示同学对具体校园问题的讨论。'+n,link:'https://example.com/latest/'+n})),reference:{value:4.5,windows:8,mae:1.2,validation_windows:4,method:'最近十日完整24小时窗口的新增帖数算术平均值'},timeline:Array.from({length:10},(_,d)=>({ts:now-(10-d)*DAY,posts:d+i,new_posts:d===3?null:d+i,observed:d!==3}))}));
const overview={success:true,generated_at:now,window_start:now-10*DAY,window_days:10,taxonomy:names,themes,total:426,total_7d:306,emotion:{积极:25,中性:250,消极:31},practice_count:7,coverage:themes[0].timeline.map(p=>({ready:p.observed})),wordcloud:['图书馆','课程','食堂','宿舍','选课','实习','志愿服务','运动','论文','校区','网络','社团','考试','实验室','学习'].map((term,i)=>({term,df:50-i*3}))};
const posts=Array.from({length:15},(_,i)=>({id:String(i),source:i%2?'tieba-school':'huyou-school',theme:names[i%12],content:'验证用示例正文。'.repeat(35),published:now-i*1000,emotion:'中性',heat:70,link:'https://example.com/post/'+i}));
let submitted=[],failResearch=false;
const server=http.createServer((req,res)=>{
 const url=new URL(req.url,'http://localhost'),p=url.pathname;
 const json=(data,status=200)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify(data));};
 if(p==='/pulse/api/revision/overview')return json(overview);
 if(p==='/pulse/api/campus')return json({success:true,voice:{crisis:{高危:1,关注:2}}});
 if(p==='/pulse/api/campus/crisis-posts')return json({success:true,posts:posts.slice(0,3),total:3,filtered_posts:posts.slice(3,5),filtered_total:2});
 if(p==='/pulse/api/revision/posts'||p==='/pulse/api/revision/source-posts')return json({success:true,posts,total:posts.length});
 if(p==='/pulse/api/revision/feed/hot')return json({success:true,platforms:['抖音','澎湃','B站','头条'],method:'formula',items:['抖音','澎湃','B站','头条'].flatMap(platform=>Array.from({length:15},(_,i)=>({platform,id:i,title:platform+'热点阅读测试'+i,rank:i+1,ts:now,signal:15-i,url:'https://example.com/hot/'+i,focus:'这是已采集报道的关注焦点摘要。'})))});
 if(p==='/pulse/api/revision/feed/memes')return json({success:true,platforms:[],items:Array.from({length:10},(_,i)=>({term:'流行表达 '+i,form:'网络流行语',meaning:'流行表达释义验证。',usage:'一般大学生活中的表达场景。',examples:['这是一句表达示例。'],evidence_status:'近期采集用例',reference_url:'https://example.com/meaning/'+i,reference_title:'释义参考',search_links:[{platform:'B站',url:'https://example.com/search/'+i}],links:[{platform:'B站',url:'https://example.com/meme/'+i,title:'实际采集的标题'}]}))});
 if(p==='/pulse/api/revision/ledger')return json({success:true,unique_school_posts:4000,reports_completed:31,unique_items:17000,sources:Object.keys({'douyin':1,'thepaper':1,'bilibili-popular':1,'bilibili-hot-search':1,'toutiao':1,'weibo':1,'baidu':1,'huyou-school':1,'tieba-school':1}).map((source,i)=>({source,unique:1000+i*200})),daily_usage:Array.from({length:14},(_,i)=>({day:'2026-10-'+String(i+7),has_records:i>0,tokens:i?i*13000:null,unknown_calls:i===2?1:0}))});
 if(p==='/pulse/api/revision/weekly/config')return json({success:true,config:{enabled:false,sender:'',recipients:[],key_configured:false,sender_verified:false,next_send:now+86400}});
 if(p==='/pulse/api/revision/weekly')return json({success:true,items:[{id:'preview_fixture',kind:'preview',cutoff:now,created:now,status:'ready',send_state:'pending'}],config:{enabled:false,sender:'',recipients:[],key_configured:false,sender_verified:false,next_send:now+86400}});
 if(p==='/pulse/api/revision/research'&&req.method==='POST'){
  let body='';req.on('data',x=>body+=x);req.on('end',()=>{submitted.push(JSON.parse(body));json(failResearch?{success:false,message:'研究服务启动失败'}:{success:true,task_id:'task_fixture'},failResearch?503:200);});return;
 }
 if(p==='/pulse/api/revision/research')return json({success:true,items:[{task_id:'task_fixture',query:'校园信息公开事件研究',created_at:now,status:'completed'}]});
 if(p==='/pulse/api/revision/research/task_fixture')return json({success:true,status:'completed',query:'研究示例',engines:{query:'completed',media:'completed',insight:'completed'}});
 if(p.endsWith('/report')){res.setHeader('Content-Type','text/html');res.end('<!doctype html><html lang="zh"><body>四章事件报告界面验证</body></html>');return;}
 if(p==='/api/config')return json({success:true,config:{}});
 const file=p==='/'||p==='/pulse/'?path.join(root,'templates/index.html'):path.join(root,p);
 if(!file.startsWith(root)||!fs.existsSync(file)){res.writeHead(404);res.end();return;}
 res.setHeader('Content-Type',file.endsWith('.html')?'text/html; charset=utf-8':file.endsWith('.css')?'text/css':file.endsWith('.js')?'text/javascript':'application/octet-stream');res.end(fs.readFileSync(file));
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
 await page.goto('http://127.0.0.1:'+server.address().port);await page.locator('#campusCategories button').first().waitFor();
 const results=[];
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:width===1440?1000:844});
  for(const tab of ['campus','trends','hot','memes','research','ledger']){
   await page.locator('[data-tab="'+tab+'"]').click();await page.waitForTimeout(100);
   assert(await page.locator('#'+tab).isVisible());
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1),false,tab+' overflow '+width);
  }
  await page.locator('[data-tab=campus]').click();assert.equal(await page.locator('#campusCategories button').count(),12);
  await page.waitForTimeout(300);await page.screenshot({path:path.join(out,'home-'+width+'.png'),fullPage:true});assert.equal(await page.locator('#campusTopics .discussion').count(),3);assert.equal(await page.locator('#campusTopics .discussion-excerpt a').count(),9);assert.equal(await page.locator('#topSize').count(),0);assert.equal(await page.locator('.home-aside section').count(),4);
  await page.locator('#campusCategories button').first().click();await page.locator('#detailBody .post').first().waitFor();
  await page.locator('#detailBody').evaluate(el=>el.scrollTop=700);
  const body=await page.locator('#detailDialog .dialog-head').boundingBox();assert(body.y>=0);
  await page.locator('#detailBody .post [data-method=emotion]').last().click();
  assert.equal(await page.locator('dialog[open]').count(),2);await page.keyboard.press('Escape');assert.equal(await page.locator('dialog[open]').count(),1);await page.keyboard.press('Escape');assert.equal(await page.locator('dialog[open]').count(),0);
  await page.locator('[data-tab=trends]').click();assert.equal(await page.locator('#trendRows tr').count(),12);assert(!(await page.locator('#trendRows').textContent()).includes('4.5'));
  await page.locator('#trendRows [data-theme-trend]').first().click();await page.locator('#detailBody .trend-chart').waitFor();assert((await page.locator('#detailBody').textContent()).includes('历史滚动平均绝对误差'));await page.keyboard.press('Escape');
  await page.waitForTimeout(300);await page.screenshot({path:path.join(out,'trends-'+width+'.png'),fullPage:true});
  await page.locator('[data-tab=hot]').click();await page.locator('#hotPlatforms [data-platform="B站"]').click();assert((await page.locator('#hotFeed').textContent()).includes('B站热点阅读测试'));assert.equal(await page.locator('#hotFeed .feed-card').count(),10);assert.equal(await page.locator('#hotFeed .hot-focus').count(),10);assert(!(await page.locator('#hotFeed').textContent()).includes('榜位'));
  await page.locator('[data-tab=memes]').click();assert.equal(await page.locator('#memePlatforms').count(),0);assert((await page.locator('#memeFeed').textContent()).includes('流行表达释义验证'));assert.equal(await page.locator('#memeFeed .feed-card').count(),10);assert.equal(await page.locator('#memeFeed .meme-reference').count(),10);await page.waitForTimeout(300);await page.screenshot({path:path.join(out,'memes-'+width+'.png'),fullPage:true});
  await page.locator('[data-tab=ledger]').click();assert.equal(await page.locator('#ledgerDonuts .donut-card').count(),3);
  const firstRing=page.locator('#ledgerDonuts .donut-card').first().locator('svg');
  for(const [index,previous] of [[0,0],[1,30]]){
   await firstRing.scrollIntoViewIfNeeded();const ringBox=await firstRing.boundingBox();
   const angle=2*Math.PI*(previous+(30+index)/2)/426;
   await firstRing.click({position:{x:ringBox.width*(64+46*Math.sin(angle))/128,y:ringBox.height*(64-46*Math.cos(angle))/128}});
   await page.locator('#detailBody .trend-chart').waitFor();
   assert((await page.locator('#detailTitle').textContent()).startsWith(names[index]),'Donut mouse segment should match category');
   await page.keyboard.press('Escape');
  }
  await page.locator('#ledgerDonuts .donut-card').first().locator('circle[role=button]').first().focus();await page.keyboard.press('Enter');await page.locator('#detailBody .trend-chart').waitFor();await page.keyboard.press('Escape');
  assert.equal(await page.locator('.usage-day').count(),14);assert.equal(await page.locator('.token-bars').count(),0);const usageColors=await page.locator('.usage-day').evaluateAll(items=>items.map(x=>getComputedStyle(x).backgroundColor));assert.equal(new Set(usageColors).size,1);const grid=await page.locator('.usage-days').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length);assert.equal(grid,width>1000?7:2);assert((await page.locator('.usage-day').first().textContent()).includes('暂无记录'));assert.equal(await page.locator('.stationery-flight').count(),1);await page.waitForTimeout(300);await page.screenshot({path:path.join(out,'ledger-'+width+'.png'),fullPage:true});await page.locator('[data-tab=research]').click();await page.locator('#researchQuery').fill('鹅腿阿姨事件，关注清华北大周边的烤鹅腿摊主');await page.waitForTimeout(800);assert(await page.locator('.mascot-stage canvas').evaluate(c=>c.getContext('2d').getImageData(0,0,c.width,c.height).data.some((x,i)=>i%4===3&&x>0)));await page.waitForTimeout(300);await page.screenshot({path:path.join(out,'research-'+width+'.png'),fullPage:true});
  results.push({width,sixModules:true,twelveCategories:true,noHorizontalOverflow:true,modalScroll:true,nativeHelpAboveModal:true,donutKeyboard:true,donutMouseSegments:true});
 }
 await page.locator('[data-tab=research]').click();assert.equal(await page.locator('#researchForm select').count(),0);
 await page.locator('#researchQuery').fill('校园信息公开的事件影响有哪些？');await page.locator('#researchSubmit').click();await page.getByText('报告已生成',{exact:true}).waitFor();
 assert(submitted[0].query&&submitted[0].request_id&&!('intent'in submitted[0])&&!('analysis_options'in submitted[0]));
 failResearch=true;await page.locator('#researchQuery').fill('服务失败时保留问题');await page.locator('#researchSubmit').click();await page.getByText('研究服务启动失败',{exact:true}).waitFor();assert.equal(await page.locator('#researchQuery').inputValue(),'服务失败时保留问题');assert(await page.locator('#researchSubmit').isEnabled());
 await page.locator('#configButton').click();await page.locator('#configDialog').waitFor({state:'visible'});assert.equal(await page.locator('#configFields .config-engine').count(),6);await page.keyboard.press('Escape');
 await page.emulateMedia({reducedMotion:'reduce'});assert.equal(await page.locator('.paper-plane').evaluate(el=>getComputedStyle(el).animationName),'none');
 await page.locator('[data-tab=campus]').click();await page.locator('#homeWeekly').click();await page.locator('#weeklyHistory [data-weekly-read]').waitFor();assert(await page.locator('#weeklyPanel').isVisible());assert(!(await page.locator('#eventPanel').isVisible()));await page.locator('#weeklyConfigure').click();await page.locator('#weeklyConfigDialog').waitFor({state:'visible'});assert.equal(await page.locator('#weeklyConfigForm input[name=api_key]').inputValue(),'');await page.keyboard.press('Escape');await page.locator('#eventViewButton').click();assert(await page.locator('#eventPanel').isVisible());
 assert.equal(errors.length,0,JSON.stringify(errors));
 const result={passed:true,checks:results,fixedTopThree:true,threeOriginalLinksEach:true,allHotCardsHaveFocus:true,tenAggregatedMemes:true,fourteenUsageDays:true,desktopSevenColumns:true,mobileTwoColumns:true,reducedMotionRespected:true,reportInputSimplified:true,originalWorkflowRequest:true,inputRetainedOnError:true,configurationAccessible:true,scriptErrors:errors,fourHomeCards:true,uniformUsageColors:true,weeklySubview:true,weeklyConfigAccessible:true,api:'mock; no real model result'};
 fs.writeFileSync(path.join(__dirname,'campus-v5-ui-results.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
 await browser.close();server.close();
})().catch(e=>{console.error(e);server.close();process.exit(1)});
