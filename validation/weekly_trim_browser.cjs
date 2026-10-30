const fs=require('fs'),assert=require('assert');
const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const dest='C:/Users/19946/Desktop/育人项目/分析资料/周报移除统计附表_20261030';
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
for(const [name,viewport] of [['desktop',{width:1280,height:1000}],['mobile',{width:390,height:844}]]){
 const page=await browser.newPage({viewport});await page.setContent(fs.readFileSync(dest+'/weekly.html','utf8'));
 assert.equal(await page.getByRole('heading',{name:'十二类议题 · 采集帖量对照',exact:true}).count(),0);
 assert.equal(await page.locator('.scope').count(),1);assert.equal(await page.locator('.report-references').count(),1);
 assert(await page.locator('body').evaluate(n=>n.scrollWidth<=innerWidth));
 await page.locator('.report-references').scrollIntoViewIfNeeded();await page.screenshot({path:dest+'/ending-'+name+'.png'});await page.close();
}await browser.close();fs.writeFileSync('validation/weekly-trim-browser-results.json',JSON.stringify({passed:true,desktop:true,mobile:true,opening_and_sources_retained:true},null,2));console.log('Desktop/mobile checks passed');})().catch(e=>{console.error(e);process.exit(1)});
