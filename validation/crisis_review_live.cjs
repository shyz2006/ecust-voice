const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const anonymous=await browser.newContext();
 const denied=await anonymous.request.get('http://127.0.0.1:15000/pulse/api/campus/crisis-posts?level='+encodeURIComponent('高危'));
 assert.equal(denied.status(),401);assert.equal(denied.headers()['cache-control'],'no-store');await anonymous.close();
 const cookie=process.env.CRISIS_REVIEW_COOKIE;assert(cookie,'Session supplied privately by SSH validation wrapper');
 delete process.env.CRISIS_REVIEW_COOKIE;
 const context=await browser.newContext();
 await context.addCookies([{name:'session',value:cookie,url:'http://127.0.0.1:15000',httpOnly:true,sameSite:'Lax'}]);
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>['GET','HEAD'].includes(route.request().method())&&new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
 await page.goto('http://127.0.0.1:15000/pulse/',{waitUntil:'domcontentloaded'});
 await page.waitForFunction(()=>/^\d+$/.test(document.getElementById('crisisHighCount')?.textContent || ''));
 const checks=[];
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:width===1440?1000:844});
  const evidence=page.locator('.campus-evidence');await evidence.evaluate(el=>el.open=false);
  for(const [index,level,id] of [[0,'高危','crisisHighCount'],[1,'关注','crisisWarnCount']]){
   const expected=Number(await page.locator('#'+id).textContent());
   await evidence.locator('summary .crisis-posts-link').nth(index).click();
   await page.locator('#postModalBody .post-list-summary').waitFor();
   const posts=await page.locator('#postModalBody .post-item-card').count();
   const links=await page.locator('#postModalBody .post-item-content a').count();
   assert.equal(posts,expected);assert.equal(links,posts);
   assert.equal(await evidence.evaluate(el=>el.open),false);
   assert.equal(await page.locator('.metric-help-panel').isVisible(),false,'Count must open posts, not metric help');
   assert(!(await page.locator('#btnForwardPostToStudio').isVisible()));
   const labels=await page.locator('#postModalBody .post-item-header > div > button:first-child').allTextContents();
   assert(labels.every(x=>x===(level==='关注'?'重点关注':'高危')));
   await page.evaluate(()=>closePostModal());checks.push({width,level,posts,links});
  }
  await evidence.locator('summary .evidence-sample').click();
  await evidence.locator('.crisis-alert-stats .crisis-posts-link').first().focus();await page.keyboard.press('Enter');
  await page.locator('#postModalBody .post-list-summary').waitFor();await page.evaluate(()=>closePostModal());
 }
 assert.equal(errors.length,0,JSON.stringify(errors));
 const result={passed:true,unauthenticated_status:401,no_store:true,checks,expanded_keyboard:true,script_errors:errors,production_writes:false};
 fs.writeFileSync(path.join(__dirname,'crisis-review-live-results.json'),JSON.stringify(result,null,2)+'\n');
 console.log(JSON.stringify(result));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
