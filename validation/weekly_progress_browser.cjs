const fs=require('fs'),assert=require('assert');
const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const dest='C:/Users/19946/Desktop/育人项目/分析资料/周报与进度优化_20261030';
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 for(const [size,viewport] of [['desktop',{width:1440,height:1100}],['mobile',{width:390,height:844}]]){
  const page=await browser.newPage({viewport});await page.setContent(fs.readFileSync(dest+'/周报结构预览.html','utf8'));
  assert.equal(await page.locator('.report-body a').count(),0);assert.equal(await page.locator('.report-references').count(),1);
  assert(await page.locator('body').evaluate(n=>n.scrollWidth<=innerWidth));
  assert(!(await page.locator('.report-body').innerText()).includes('事件全景'));
  await page.screenshot({path:dest+'/weekly-'+size+'.png',fullPage:true});
  if(size==='desktop')await page.pdf({path:dest+'/weekly.pdf',format:'A4',printBackground:true});await page.close();
 }
 const source=fs.readFileSync('production/static/js/campus-review.js','utf8'),start=source.indexOf('async function pollTask('),end=source.indexOf('let briefVersion=',start);
 const page=await browser.newPage({viewport:{width:390,height:844}});
 await page.setContent('<div id="researchProgress"></div><button id="researchSubmit"></button>');
 await page.evaluate(async code=>{
  const $=id=>document.getElementById(id),state={},esc=s=>String(s??'').replace(/</g,'&lt;'),num=v=>String(v),api=async()=>({status:'reporting',engines:{query:'completed',media:'completed',insight:'completed'},report_detail:{completed_chapters:2,total_chapters:5},message:'第三章 · 核对来源，第2次尝试'}),setTimeout=()=>0;
  await eval('('+code.trim()+')')( 'task_test');
 },source.slice(start,end));
 const text=await page.locator('#researchProgress').innerText();assert(text.includes('已核验 2 / 5 章'));assert(text.includes('核对来源，第2次尝试'));
 await page.screenshot({path:dest+'/report-progress-mobile.png'});await browser.close();
 fs.writeFileSync('validation/weekly-progress-browser-results.json',JSON.stringify({passed:true,weekly_desktop:true,weekly_mobile:true,pdf:true,actual_poll_function:true},null,2)+'\n');console.log('Preview and actual progress UI passed');
})().catch(e=>{console.error(e);process.exit(1)});
