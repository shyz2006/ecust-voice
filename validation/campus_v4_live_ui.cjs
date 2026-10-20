const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const context=await browser.newContext(),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{
  const request=route.request(),url=new URL(request.url());
  if(request.method()!=='GET'||url.hostname!=='127.0.0.1')return route.abort();
  const files={'/':'templates/index.html','/static/css/campus-play.css':'static/css/campus-play.css','/static/js/campus-play.js':'static/js/campus-play.js','/static/css/campus-review.css':'static/css/campus-review.css','/static/js/campus-review.js':'static/js/campus-review.js'};
  if(files[url.pathname])return route.fulfill({path:path.resolve(__dirname,'../production',files[url.pathname]),contentType:url.pathname.endsWith('.css')?'text/css':url.pathname.endsWith('.js')?'text/javascript':'text/html; charset=utf-8'});
  return route.continue();
 });
 const base=process.env.VALIDATION_BASE||'http://127.0.0.1:15003';
 await context.request.get(base+'/validation/login');
 await page.goto(base+'/');
 try{await page.locator('#campusCategories button').first().waitFor({timeout:45000});}catch(e){console.log('Page diagnostics:',errors,await page.locator('#campusTopics').textContent());throw e;}
 const checks=[];
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:width===1440?1000:844});
  for(const tab of ['campus','trends','hot','memes','research','ledger']){
   await page.locator('[data-tab='+tab+']').click();
   const ready={campus:'#campusCategories button',trends:'#trendRows tr',hot:'#hotFeed .feed-item',memes:'#memeFeed .meme-entry',research:'#researchHistory',ledger:'#ledgerDonuts .donut-card'};
   if(tab==='hot'){await page.locator('#hotFeed .feed-card a').first().waitFor({timeout:45000});assert.equal(await page.locator('#hotFeed .feed-card').count(),10);assert.equal(await page.locator('#hotFeed .hot-focus').count(),10);assert(!(await page.locator('#hotFeed').textContent()).includes('榜位'));}
   else if(tab==='memes'){
    const feed=await context.request.get(base+'/pulse/api/revision/feed/memes'),data=await feed.json();
    assert.equal(data.items.length,10);assert.equal(new Set(data.items.map(x=>x.term)).size,10);assert(data.items.some(x=>x.links.length),'Expected actual observed examples');
    assert.equal(await page.locator('#memePlatforms').count(),0);
    await page.locator('#memeFeed .feed-card a').first().waitFor({timeout:45000});assert.equal(await page.locator('#memeFeed .feed-card').count(),10);
   }else await page.locator(ready[tab]).first().waitFor({timeout:45000});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,tab+' overflow');
  }
  await page.locator('[data-tab=ledger]').click();assert.equal(await page.locator('.usage-day').count(),14);
  await page.locator('[data-tab=campus]').click();assert.equal(await page.locator('#campusTopics .discussion').count(),3);assert.equal(await page.locator('#campusTopics .discussion-excerpt a').count(),9);assert.equal(await page.locator('#campusCategories button').count(),12);
  await page.locator('#campusCategories button').first().click();await page.locator('#detailBody .post').first().waitFor({timeout:45000});
  const links=await page.locator('#detailBody .post a').count();assert(links>0);
  await page.locator('#detailBody .post [data-method=emotion]').first().click();assert.equal(await page.locator('dialog[open]').count(),2);
  await page.keyboard.press('Escape');await page.keyboard.press('Escape');
  await page.evaluate(()=>document.activeElement?.blur());
  await page.waitForTimeout(300);await page.screenshot({path:path.resolve(__dirname,'../../validation-artifacts/campus-v4/real-home-'+width+'.png'),fullPage:true});
  checks.push({width,sixModules:true,twelveCategories:true,originalLinks:links,nestedHelpVisible:true,noHorizontalOverflow:true});
 }
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(__dirname,'campus-v4-live-ui-results.json'),JSON.stringify({passed:true,data:'isolated copy of production data',checks,errors},null,2));
 await browser.close();console.log('Real-data browser checks passed');
})().catch(e=>{console.error(e);process.exit(1)});
