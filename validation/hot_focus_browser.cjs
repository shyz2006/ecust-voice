const fs=require('fs'),assert=require('assert');
const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const dest='C:/Users/19946/Desktop/育人项目/分析资料/热点概括与周报样式_20261030';
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 for(const [size,viewport] of [['desktop',{width:1280,height:1050}],['mobile',{width:390,height:844}]]){
  const page=await browser.newPage({viewport});await page.setContent(fs.readFileSync(dest+'/weekly.html','utf8'));
  const style=await page.locator('.scope').evaluate(n=>{const a=getComputedStyle(n),b=getComputedStyle(n.querySelector('h2')),c=getComputedStyle(document.querySelector('.report-body h2'));return {background:a.backgroundColor,padding:a.padding,font:b.fontSize,otherFont:c.fontSize,color:b.color,otherColor:c.color};});
  assert.equal(style.background,'rgba(0, 0, 0, 0)');assert.equal(style.padding,'0px');assert.equal(style.font,style.otherFont);assert.equal(style.color,style.otherColor);
  assert(await page.locator('body').evaluate(n=>n.scrollWidth<=innerWidth));await page.screenshot({path:dest+'/weekly-'+size+'.png'});await page.close();
 }
 const source=fs.readFileSync('production/static/js/campus-review.js','utf8'),start=source.indexOf('function renderFeed('),end=source.indexOf('function signalPill(',start);
 const css=fs.readFileSync('production/static/css/campus-review.css','utf8');
 const page=await browser.newPage({viewport:{width:1100,height:900}});await page.setContent('<style>'+css+'</style><div id="hotPlatforms"></div><div id="hotFeed"></div>');
 const fixture=fs.existsSync(dest+'/hot.json')?JSON.parse(fs.readFileSync(dest+'/hot.json','utf8')):{focus_pending:true,platforms:['抖音'],items:[{platform:'抖音',title:'大学开放夜间自习室',focus:'自习空间的开放安排涉及晚间学习便利与校园服务的配合。',focus_method:'llm_summary'}]};
 await page.evaluate(({code,data})=>{
  const $=id=>document.getElementById(id),state={hotPlatform:data.platforms[0],tab:'hot'},esc=s=>String(s??'').replace(/</g,'&lt;'),date=()=>'',signalPill=()=>'',sourceLink=()=>'',sourceSearchUrl=()=>null,renderMemes=()=>{},empty=s=>s;let hotFocusPoll;
  window.pollQueued=false;const setTimeout=()=>{window.pollQueued=true;return 1},clearTimeout=()=>{};
  eval('('+code.trim()+')')('hot',data);
 },{code:source.slice(start,end),data:fixture});
 assert((await page.locator('.hot-focus p').allTextContents()).every(x=>x.trim()));assert.equal(await page.locator('.hot-focus h3').first().innerText(),'关注焦点');
 await page.screenshot({path:dest+'/hot-desktop.png',fullPage:true});await browser.close();
 fs.writeFileSync('validation/hot-focus-browser-results.json',JSON.stringify({passed:true,uniform_weekly_sections:true,desktop:true,mobile:true,actual_focus_renderer:true},null,2)+'\n');console.log('Weekly and focus UI checks passed');
})().catch(e=>{console.error(e);process.exit(1)});
