const fs=require('fs'),assert=require('assert');
const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const dest='C:/Users/19946/Desktop/育人项目/分析资料/周报正式结构_20261030';
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});let refs=0;
 for(const [size,viewport] of [['desktop',{width:1280,height:1100}],['mobile',{width:390,height:844}]]){
  const page=await browser.newPage({viewport});await page.setContent(fs.readFileSync(dest+'/weekly-formal.html','utf8'));
  assert.equal(await page.locator('.scope a,.report-body a').count(),0);
  assert(!/\[(?:S\d+|\d+)|https?:\/\//.test(await page.locator('.scope,.report-body').allInnerTexts().then(xs=>xs.join(' '))));
  assert.equal(await page.locator('.report-body > section').count(),3);
  assert.equal(await page.locator('.report-references').count(),1);refs=await page.locator('.report-references a').count();assert(refs>0);
  assert(await page.locator('body').evaluate(n=>n.scrollWidth<=innerWidth));
  const headings=await page.locator('h2').allTextContents();assert(headings[0].startsWith('一、'));assert(headings[3].startsWith('四、'));
  await page.screenshot({path:dest+'/formal-'+size+'.png'});await page.screenshot({path:dest+'/formal-'+size+'-full.png',fullPage:true});
  if(size==='desktop')await page.pdf({path:dest+'/校园周报_正式结构预览.pdf',format:'A4',printBackground:true});await page.close();
 }
 await browser.close();fs.writeFileSync('validation/weekly-formal-browser-results.json',JSON.stringify({passed:true,desktop:true,mobile:true,pdf:true,inline_links:0,inline_citations:0,appendix_links:refs},null,2)+'\n');console.log('Formal weekly browser checks passed');
})().catch(e=>{console.error(e);process.exit(1)});
