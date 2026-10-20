const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('assert');
const root=path.resolve(__dirname,'../production'),out=path.resolve(__dirname,'../../validation-artifacts/meme-cards');
const data=JSON.parse(fs.readFileSync(path.join(out,'real-memes.json'),'utf8'));
const server=http.createServer((req,res)=>{
 const p=new URL(req.url,'http://localhost').pathname;
 if(p.startsWith('/pulse/api/')){
  res.setHeader('Content-Type','application/json');
  res.end(JSON.stringify(p.endsWith('/feed/memes')?{success:true,...data}:p.endsWith('/weekly/config')?{success:true,config:{schedule:'每周定时'}}:{success:true,voice:{crisis:{高危:0,关注:0}}}));return;
 }
 const file=p==='/'?path.join(root,'templates/index.html'):path.join(root,p);
 if(!file.startsWith(root)||!fs.existsSync(file)){res.writeHead(404);res.end();return;}
 res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.html')?'text/html; charset=utf-8':'application/octet-stream');res.end(fs.readFileSync(file));
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage(),errors=[],checks=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
 await page.goto('http://127.0.0.1:'+server.address().port+'/#memes');
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:width===1440?1000:844});await page.locator('#memeFeed .meme-card').first().waitFor();
  assert.equal(await page.locator('#memeFeed .meme-card').count(),10);assert.equal(await page.locator('#memes details').count(),0);
  const intros=await page.locator('#memeFeed .meme-intro p').allTextContents();assert(intros.every(x=>x.length>=12));
  const uses=await page.locator('#memeFeed .meme-uses').evaluateAll(items=>items.map(x=>[...x.querySelectorAll('a')].map(a=>a.href)));
  assert(uses.every(urls=>urls.length>=1&&urls.every(url=>!url.includes('/search')&&!url.includes('search.bilibili.com'))));
  assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)));
  await page.screenshot({path:path.join(out,'real-memes-'+width+'.png'),fullPage:true});checks.push({width,cards:10,allIntroductions:true,allUseLinks:true,noFolding:true,noHorizontalOverflow:true});
 }
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(__dirname,'meme-cards-live-ui-results.json'),JSON.stringify({passed:true,data:'actual model output from isolated production copy',verified:data.items.length,candidates:data.candidates.length,checks,errors},null,2)+'\n');
 await browser.close();server.close();console.log(JSON.stringify({passed:true,checks}));
})().catch(e=>{console.error(e);server.close();process.exit(1)});
