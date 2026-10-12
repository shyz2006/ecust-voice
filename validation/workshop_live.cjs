const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const out=path.resolve(__dirname,'../../validation-artifacts');
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 // Read-only live checks: never submit a model job or update production records.
 await page.route('**/*',async route=>{
  const req=route.request();
  if(!['GET','HEAD'].includes(req.method()))return route.abort();
  if(new URL(req.url()).hostname!=='127.0.0.1')return route.abort();
  return route.continue();
 });
 await page.goto('http://127.0.0.1:15000/pulse/',{waitUntil:'domcontentloaded'});
 await page.waitForTimeout(1500);
 await page.evaluate(()=>heroGoStudio());
 assert(await page.locator('#studioQueryInput').isVisible());
 assert.equal(await page.locator('#studioQueryInput').evaluate(el=>!!el.closest('details')),false);
 assert.equal(await page.locator('#studioQueryInput').evaluate(el=>document.activeElement===el),true);
 await page.locator('#studioQueryInput').fill('如何核实校园食堂晚间服务需求？');
 await page.locator('#directionTrigger').click();assert(await page.locator('#selectPsychLens').isVisible());
 await page.getByRole('button',{name:'完成',exact:true}).click();
 await page.locator('#pane-studio .studio-box').screenshot({path:path.join(out,'workshop-live.png')});
 await page.getByRole('button',{name:'根据原帖研究',exact:true}).click();assert(await page.locator('#issueChooser').isVisible());
 await page.evaluate(()=>forwardToStudio('华理校园食堂晚间服务核查建议'));
 assert.equal(await page.locator('#studioQueryInput').inputValue(),'华理校园食堂晚间服务核查建议');
 assert.equal(errors.length,0,JSON.stringify(errors));
  let modalPosts=0;
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:width===1440?1000:844});
   await page.evaluate(()=>viewCampusPosts('校园设施与管理'));
   await page.locator('#postModalBody .post-item-card').first().waitFor();await page.waitForTimeout(250);
   modalPosts=await page.locator('#postModalBody .post-item-card').count();
   assert.equal(await page.locator('#postModalBody .post-list-summary').evaluate(e=>getComputedStyle(e).position),'static');
   assert.equal(await page.evaluate(()=>document.body.style.overflow),'hidden');
   const background=await page.evaluate(()=>window.scrollY);
   await page.locator('#postModalBody').evaluate(e=>e.scrollTop=600);
   const bodyBox=await page.locator('#postModalBody').boundingBox(),summaryBox=await page.locator('#postModalBody .post-list-summary').boundingBox();
   assert(summaryBox.y+summaryBox.height<bodyBox.y);
   await page.locator('#postModalBody').hover();await page.mouse.wheel(0,300);await page.waitForTimeout(100);
   assert.equal(await page.evaluate(()=>window.scrollY),background);
   assert(!(await page.locator('#postModalBody').textContent()).includes('脱敏'));
   await page.evaluate(()=>closePostModal());await page.waitForTimeout(50);
   assert.notEqual(await page.evaluate(()=>document.body.style.overflow),'hidden');
  }
 // Public Cloudflare/TLS route: verify login page without accessing credentials.
 const response=await browser.newContext().then(c=>c.request.get('https://smydashuaige.2026515.xyz/login'));
 assert.equal(response.status(),200);assert((await response.text()).includes('password'));
 const result={passed:true,live_page:'via authenticated SSH tunnel to running application',public_login_http_status:response.status(),question_visible:true,source_chooser:true,post_modal_scroll:true,post_modal_posts:modalPosts,script_errors:errors,production_writes:false};
 fs.writeFileSync(path.join(out,'live-results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
