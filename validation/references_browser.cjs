const fs=require('fs'),assert=require('assert');
const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const dest='C:/Users/19946/Desktop/育人项目/分析资料/报告引用调整_20261030';
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});const results=[];
 for(const kind of ['event','weekly'])for(const [size,viewport] of [['desktop',{width:1440,height:1100}],['mobile',{width:390,height:844}]]){
  const html=fs.readFileSync(dest+'/'+kind+'.html','utf8'),page=await browser.newPage({viewport}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent(html,{waitUntil:'load'});if(kind==='event')await page.evaluate('window.reportReady');
  assert.equal(await page.locator('.report-body a[href]').count(),0);
  assert(!/https?:\/\/|\[S\d+\]/.test(await page.locator('.report-body').innerText()));
  assert.equal(await page.locator('.report-references').count(),1);
  assert((await page.locator('.report-references a[href]').count())>0);
  assert(await page.locator('.report-references').evaluate(n=>!n.nextElementSibling||n.nextElementSibling.tagName==='FOOTER'));
  if(kind==='weekly'){
   const summary=await page.locator('.scope').innerText();assert(summary.includes('20 篇'));assert(summary.includes('3 类议题'));
   assert(await page.locator('.scope').evaluate(n=>!!(n.compareDocumentPosition(document.querySelector('.report-body'))&Node.DOCUMENT_POSITION_FOLLOWING)));
   assert.equal(await page.locator('script').count(),0);
  }else{assert.equal(await page.locator('canvas').count(),2);assert.equal(await page.locator('.mermaid svg').count(),1);}
  assert.deepEqual(errors,[]);await page.screenshot({path:dest+'/'+kind+'-'+size+'.png',fullPage:true});
  if(size==='desktop')await page.pdf({path:dest+'/'+kind+'.pdf',format:'A4',printBackground:true,preferCSSPageSize:true});
  results.push({kind,viewport:size,body_links:0,final_appendix:true,weekly_summary:kind==='weekly'});await page.close();
 }
 await browser.close();fs.writeFileSync('validation/references-browser-results.json',JSON.stringify({passed:true,results,pdf:true},null,2)+'\n');console.log(JSON.stringify({passed:true,results,pdf:true}));
})().catch(e=>{console.error(e);process.exit(1)});
