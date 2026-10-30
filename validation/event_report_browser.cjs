const fs=require('fs'),assert=require('assert');
const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const dest='C:/Users/19946/Desktop/育人项目/分析资料/事件报告修复_20261030';
const html=fs.readFileSync(dest+'/报告渲染预览.html','utf8');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});const results=[];
 for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
  const page=await browser.newPage({viewport});const errors=[],requests=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/')return route.fulfill({contentType:'text/html',body:'<iframe title="报告" sandbox="allow-scripts allow-popups" style="width:100%;height:96vh;border:0" src="/report"></iframe>'});
   if(path==='/report')return route.fulfill({contentType:'text/html',headers:{'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src https: data:; font-src 'self'"},body:html});
   requests.push(route.request().url());return route.abort();
  });
  await page.goto('https://reports.example.invalid/');const frame=page.frames().find(f=>f.url().endsWith('/report'));
  await frame.waitForFunction('window.reportRenderComplete === true',{timeout:30000});
  assert.equal(await frame.locator('canvas').count(),2);assert.equal(await frame.locator('.mermaid svg').count(),1);
  assert((await frame.locator('table').count())>=4);assert((await frame.locator('strong').count())>=2);
  const plots=await frame.locator('canvas').evaluateAll(nodes=>nodes.map(n=>({width:n.width,height:n.height})));assert(plots.every(p=>p.width>200&&p.height>150));
  assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
  await page.screenshot({path:dest+'/'+name+'.png',fullPage:true});
  results.push({viewport:name,charts:2,mermaid:1,markdown:true,offline:true});await page.close();
 }
 const page=await browser.newPage();await page.setContent(html,{waitUntil:'load'});await page.evaluate('window.reportReady');
 await page.pdf({path:dest+'/报告渲染预览.pdf',format:'A4',printBackground:true,preferCSSPageSize:true});
 await browser.close();fs.writeFileSync('validation/event-report-browser-results.json',JSON.stringify({passed:true,results,pdf:true},null,2)+'\n');console.log(JSON.stringify({passed:true,results,pdf:true}));
})().catch(e=>{console.error(e);process.exit(1)});
