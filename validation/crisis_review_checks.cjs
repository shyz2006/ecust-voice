const assert=require('assert');
module.exports=async function checkCrisisReview(page){
 let mode='ready';const requests=[];
 const pattern='**/pulse/api/campus/crisis-posts?*';
 await page.route(pattern,async route=>{
  const level=new URL(route.request().url()).searchParams.get('level');requests.push(level);
  const status=mode==='unauthorized'?401:mode==='error'?500:200;
  const posts=mode==='empty'?[]:[{source:'huyou-school',content:'风险核查界面验证样例，仅供布局验证。',crisis_level:level,emotion:'中性',published:1791763200,link:'https://example.com/risk-review-fixture'}];
  const data=status===200?{success:true,level,posts,total:posts.length,days:7,generated_at:1791763200}:{success:false,message:mode==='unauthorized'?'请登录后查看关注帖子':'关注帖子读取失败'};
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
 });
 await page.evaluate(()=>switchTab('campus'));
 const details=page.locator('.campus-evidence');
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:width===1440?1000:844});
  await details.evaluate(el=>el.open=false);
  for(const level of ['高危','关注']){
   const button=details.locator('summary .crisis-posts-link').nth(level==='高危'?0:1);
   await button.click();await page.locator('#postModalBody .post-item-card').waitFor();
   assert.equal(await details.evaluate(el=>el.open),false,'Clicking risk link should keep summary collapsed');
   assert.equal(requests.at(-1),level);
   assert((await page.locator('#postModalBody').textContent()).includes(level==='关注'?'重点关注':'高危'));
   assert.equal(await page.locator('#postModalBody .post-item-content a').getAttribute('href'),'https://example.com/risk-review-fixture');
   assert(!(await page.locator('#btnForwardPostToStudio').isVisible()));
   await page.evaluate(()=>closePostModal());
  }
  await details.locator('summary .evidence-sample').click();
  const expanded=details.locator('.crisis-alert-stats .crisis-posts-link').first();
  await expanded.focus();await page.keyboard.press('Enter');
  await page.locator('#postModalBody .post-item-card').waitFor();assert.equal(requests.at(-1),'高危');
  await page.evaluate(()=>closePostModal());
 }
 for(const scenario of ['empty','unauthorized','error']){
  mode=scenario;await page.evaluate(()=>viewCrisisPosts('关注'));
  await page.locator('#postModalBody .empty-state').waitFor();
  assert.equal(await page.locator('#postModalBody .post-item-card').count(),0);
  const text=await page.locator('#postModalBody').textContent();
  assert(text.includes(scenario==='empty'?'暂无对应帖子':scenario==='unauthorized'?'请登录':'读取失败'));
  await page.evaluate(()=>closePostModal());
 }
 await page.unroute(pattern);
 await page.evaluate(()=>viewCampusPosts('校园设施与管理'));
 await page.locator('#postModalBody .post-item-card').first().waitFor();assert(await page.locator('#btnForwardPostToStudio').isVisible());
 await page.evaluate(()=>closePostModal());
 return {passed:true,widths:[1440,390],levels:['高危','关注'],collapsedAndExpanded:true,keyboard:true,sourceLink:true,zeroAndFailureStates:true,ordinaryPostModalRestored:true};
};
