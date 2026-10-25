const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const src=fs.readFileSync('production/static/js/campus-review.js','utf8');
const prefix=src.slice(src.indexOf('const $='),src.indexOf('const DAY='));
const funcs=src.slice(src.indexOf('function fullChart('),src.indexOf('async function openTrend('));
const fixture=JSON.parse(fs.readFileSync('validation/trend-chart-fixture.json','utf8'));
const context={document:{},theme:fixture.themes[0]};
const content=vm.runInNewContext(prefix+'const DAY=86400;'+funcs+';trendDetail(theme)',context);
let html=fs.readFileSync('production/templates/index.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'').replace(/<link[^>]*rel="stylesheet"[^>]*>/g,'');
html=html.replace('</head>','<style>'+fs.readFileSync('production/static/css/campus-review.css','utf8')+'\n'+fs.readFileSync('production/static/css/campus-play.css','utf8')+'</style></head>');
const dest='C:/Users/19946/Desktop/育人项目/分析资料/趋势图修复预览_20261025';fs.mkdirSync(dest,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const results=[];
 for(const [name,size] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
  const page=await browser.newPage({viewport:size,deviceScaleFactor:1,timezoneId:'Asia/Shanghai'});
  await page.setContent(html);
  await page.evaluate(({content,name,total})=>{document.getElementById('detailTitle').textContent=name+' · 走势与原帖';document.getElementById('detailBody').innerHTML=content+'<h3 class="post-group-title">对应原帖 · '+total+' 条</h3>';document.getElementById('detailDialog').showModal();},{content,name:fixture.themes[0].theme,total:fixture.themes[0].posts});
  await page.locator('.trend-reference-card').waitFor();
  assert.equal(await page.locator('.observed-point:visible').count(),fixture.themes[0].timeline.filter(x=>x.new_posts!=null).length);
  assert.equal(await page.locator('.reference-projection').count(),0);assert(await page.locator('.collection-gap').count()>0);
  assert.equal(await page.locator('.trend-method').getAttribute('open'),null);
  const labels=await page.locator('.trend-chart:visible .trend-date-label').evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return {left:r.left,right:r.right};}));
  for(let i=1;i<labels.length;i++)assert(labels[i].left>=labels[i-1].right,'Date labels overlap');
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);assert(!overflow);
  const modal=await page.locator('#detailDialog').boundingBox();assert(modal.x>=0&&modal.x+modal.width<=size.width+1);
  await page.screenshot({path:path.join(dest,name+'.png')});
  await page.locator('.trend-method summary').click();assert(await page.locator('.trend-method').evaluate(e=>e.open));
  results.push({viewport:name,document_overflow:false,modal_fits:true,date_labels_do_not_overlap:true,gap_not_plotted_as_low_count:true,separate_reference_card:true,methods_expand:true});
  await page.close();
 }
 for(const [name,theme] of [
 ['zero',{...fixture.themes[0],timeline:fixture.themes[0].timeline.map(p=>({...p,new_posts:0,posts:0,observed:true})),posts:0,posts_24h:0,comparison:{value:0,basis:'current'},reference:{value:0,windows:10}}],
 ['missing',{...fixture.themes[0],timeline:fixture.themes[0].timeline.map(p=>({...p,new_posts:null,posts:0,observed:false})),comparison:{value:null},reference:{value:null,windows:0}}],
 ['isolated',{...fixture.themes[0],timeline:fixture.themes[0].timeline.map((p,i)=>({...p,new_posts:i===5?10:null,posts:i===5?10:0,observed:i===5})),comparison:{value:null},reference:{value:null,windows:1}}]
 ]){
  const page=await browser.newPage({viewport:{width:390,height:844}});const fragment=vm.runInNewContext(prefix+'const DAY=86400;'+funcs+';trendDetail(theme)',{document:{},theme});
  assert(!/NaN|undefined/.test(fragment));await page.setContent(html);
  await page.evaluate(content=>{document.getElementById('detailBody').innerHTML=content;document.getElementById('detailDialog').showModal();},fragment);
  assert.equal(await page.locator('.observed-point:visible').count(),theme.timeline.filter(p=>p.new_posts!=null).length);
  const value=await page.locator('.trend-reference-number').innerText();assert(name==='zero'?value.includes('0'):value.includes('—'));
  assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth));results.push({case:name,passed:true});await page.close();
 }
 await browser.close();
 fs.writeFileSync('validation/trend-chart-browser-results.json',JSON.stringify({passed:true,results},null,2)+'\n');console.log(JSON.stringify({passed:true,previews:dest,results}));
})().catch(e=>{console.error(e);process.exit(1)});
