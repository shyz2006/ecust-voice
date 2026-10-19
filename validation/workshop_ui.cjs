const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('assert');
const root=path.resolve(__dirname,'../production');
const out=path.resolve(__dirname,'../../validation-artifacts');fs.mkdirSync(out,{recursive:true});
let scenario='idle',submitted=[],jobCalls=0;
const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost');
  if(url.pathname.startsWith('/pulse/api/')){
    let data={success:false,message:'离线验证：未连接生产数据'};let status=200;
    if(url.pathname==='/pulse/api/analyze'){
      let body='';req.on('data',d=>body+=d);req.on('end',()=>{
        submitted.push(JSON.parse(body));
        res.writeHead(scenario==='rate-limit'?429:200,{'Content-Type':'application/json'});
        res.end(JSON.stringify(scenario==='rate-limit'?{success:false,message:'当前分析任务较多，请稍后再试'}:{success:true,job_id:'validation-job'}));
      });return;
    }
    if(url.pathname.includes('/job/')){
      jobCalls++;
      if(scenario==='error')data={success:true,status:'error',error:'模型服务不可用',trace:[]};
      else if(scenario==='expired'){status=404;data={success:false,message:'任务不存在或已过期'};}
      else if(scenario==='unknown')data={success:true,status:'unexpected',trace:[]};
      else if(scenario==='degraded')data={success:true,status:'done',trace:[],result:{id:1,degraded:true}};
      else if(scenario==='no-report')data={success:true,status:'done',trace:[],result:{}};
      else data={success:true,status:jobCalls===1?'running':'done',trace:[],result:{id:1,status:'formal',verdict:{passed:true}}};
    }
    if(url.pathname==='/pulse/api/issues')data={success:true,items:[]};
    if(url.pathname==='/pulse/api/observatory/posts')data={success:true,posts:[],total:0,generated_at:Math.floor(Date.now()/1000)};
    if(url.pathname==='/pulse/api/analyses')data={success:true,items:[]};
    if(url.pathname==='/pulse/api/campus/posts')data={success:true,total:20,posts:Array.from({length:20},(_,i)=>({source:'huyou-school',content:`原帖阅读测试 ${i+1}：`+'这是用于验证滚动布局的示例正文。'.repeat(12),gist:'验证滚动布局的示例，不代表学校真实事件。',emotion:'中立',heat:77,psych_dimensions:[],published:1791763200,link:'https://example.com/post/'+i}))};
    if(url.pathname==='/pulse/api/analysis/1')data={success:true,query:'验证用样例（模拟结果）',result:{summary:'此内容仅验证结果展示，不代表模型验收。',id:1}};
    res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(data));return;
  }
  const file=url.pathname==='/'?path.join(root,'templates/index.html'):path.join(root,url.pathname);
  if(!file.startsWith(root)||!fs.existsSync(file)){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',file.endsWith('.html')?'text/html; charset=utf-8':file.endsWith('.css')?'text/css':file.endsWith('.js')?'text/javascript':'image/jpeg');res.end(fs.readFileSync(file));
});
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
  await page.goto('http://127.0.0.1:'+server.address().port);await page.waitForTimeout(500);
  await page.evaluate(()=>switchTab('studio'));
  await page.locator('#studioQueryInput').waitFor({state:'visible'});
  assert.equal(await page.locator('#studioQueryInput').evaluate(el=>!!el.closest('details')),false);
  assert(await page.locator('#researchComposer').evaluate(el=>el.closest('.studio-box').compareDocumentPosition(document.querySelector('#issueWorkbench'))&Node.DOCUMENT_POSITION_FOLLOWING));
  await page.evaluate(()=>heroGoStudio());assert.equal(await page.locator('#studioQueryInput').evaluate(el=>el===document.activeElement),true);
  await page.evaluate(()=>forwardToStudio('华理校园食堂晚间服务有哪些改进建议？'));
  assert.equal(await page.locator('#issueChooser').isVisible(),false);
  assert((await page.locator('#studioQueryInput').inputValue()).includes('华理'));
  await page.locator('#pane-studio').screenshot({path:path.join(out,'workshop-desktop.png')});
  await page.locator('#studioQueryInput').fill('');await page.locator('#btnLaunchStudio').click();
  assert.equal(submitted.length,0);assert(await page.locator('#studioInputError').isVisible());
  await page.evaluate(()=>document.querySelector('#studioQueryInput').value='问'.repeat(201));await page.locator('#btnLaunchStudio').click();assert.equal(submitted.length,0);
  const query='如何核实校园食堂晚间服务需求？';
  for(const effort of ['lean','standard','deep']){
    scenario='rate-limit';await page.locator('#studioQueryInput').fill(query);
    await page.evaluate(e=>chooseThinking(e),effort);
    await page.locator('#directionTrigger').click();
    await page.locator('#selectPsychLens').selectOption('needs');await page.locator('#selectIdeology').selectOption('actions');
    await page.getByRole('button',{name:'完成',exact:true}).click();
    await page.locator('#workshopPurpose').selectOption('activity_design');await page.locator('#btnLaunchStudio').click();
    await page.waitForFunction(()=>!document.querySelector('#btnLaunchStudio').disabled);
    const request=submitted.at(-1);assert.equal(request.query,query);assert.equal(request.workflow,{lean:'lean',standard:'lean_verified',deep:'central_verified'}[effort]);
    assert.equal(request.intent,'activity_design');assert.equal(request.analysis_options.psych_lens,'needs');assert.equal(request.analysis_options.ideology,'actions');
    assert.equal(await page.locator('#studioQueryInput').inputValue(),query);
  }
  for(const state of ['error','expired','unknown','degraded','no-report']){
    scenario=state;jobCalls=0;await page.locator('#btnLaunchStudio').click();
    await page.waitForFunction(()=>!document.querySelector('#btnLaunchStudio').disabled);
    assert.equal(await page.locator('#timelinePercent').textContent(),'失败');assert.equal(await page.locator('#studioCompleteBar').isVisible(),false);
    assert.equal(await page.locator('#studioQueryInput').inputValue(),query);
  }
  scenario='done';jobCalls=0;await page.locator('#btnLaunchStudio').click();
  await page.waitForFunction(()=>!document.querySelector('#btnLaunchStudio').disabled);
  assert(await page.locator('#studioCompleteBar').isVisible());
  await page.locator('#btnOpenGeneratedReport').click();await page.locator('#reportModalBody').getByText('此内容仅验证结果展示，不代表模型验收。',{exact:false}).waitFor();
  await page.evaluate(()=>document.querySelector('#reportModal').classList.remove('open'));
  await page.getByRole('button',{name:'根据原帖研究',exact:true}).click();assert(await page.locator('#issueChooser').isVisible());
  assert(await page.locator('#studioQueryInput').isVisible());
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>heroGoStudio());
  await page.evaluate(()=>{document.querySelector('#studioTimeline').style.display='none';document.querySelector('#issueChooser').hidden=true;});
  await page.locator('#pane-studio').screenshot({path:path.join(out,'workshop-mobile.png')});
  for(const width of [1440,390]){
    await page.setViewportSize({width,height:width===1440?1000:844});
    await page.evaluate(()=>viewCampusPosts('校园设施与管理'));
    await page.locator('#postModalBody .post-item-card').first().waitFor();
    await page.waitForTimeout(250);
    for(const label of ['中立','来源内热度 77/100']){
      const badge=page.locator('#postModalBody').getByRole('button',{name:label,exact:true}).first();
      await badge.click();const help=page.locator('.metric-help-panel');await help.waitFor({state:'visible'});
      assert(await help.evaluate(el=>{const r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}),'Help must be above modal and receive pointer input');
      await page.keyboard.press('Tab');assert(await help.locator('button').evaluate(el=>el===document.activeElement));
      await page.keyboard.press('Escape');assert.equal(await help.isVisible(),false);assert(await page.locator('#postModal').isVisible());
      assert(await badge.evaluate(el=>el===document.activeElement));
    }
    await page.locator('#postModalBody').getByRole('button',{name:'中立',exact:true}).first().focus();await page.keyboard.press('Enter');
    assert(await page.locator('.metric-help-panel').isVisible());await page.locator('.metric-help-panel button').click();
    assert.equal(await page.locator('#postModalBody .post-list-summary').evaluate(el=>getComputedStyle(el).position),'static');
    assert.equal(await page.evaluate(()=>getComputedStyle(document.body).overflow),'hidden');
    const backgroundY=await page.evaluate(()=>window.scrollY);
    await page.locator('#postModalBody').evaluate(el=>el.scrollTop=480);
    const bodyBox=await page.locator('#postModalBody').boundingBox();
    const summaryBox=await page.locator('#postModalBody .post-list-summary').boundingBox();
    assert(summaryBox.y+summaryBox.height<bodyBox.y,'Summary should scroll away without overlaying posts');
    const headerBox=await page.locator('#postModal .modal-header').boundingBox(),footerBox=await page.locator('#postModal .modal-footer').boundingBox();
    assert(headerBox.y>=0&&footerBox.y+footerBox.height<= (width===1440?1000:844)+1);
    await page.locator('#postModalBody').hover();await page.mouse.wheel(0,400);await page.waitForTimeout(150);
    assert.equal(await page.evaluate(()=>window.scrollY),backgroundY);
    assert(!(await page.locator('#postModalBody').textContent()).includes('脱敏'));
    await page.locator('#postModal').screenshot({path:path.join(out,`post-modal-${width}.png`)});
    await page.evaluate(()=>closePostModal());await page.waitForTimeout(50);
    assert.notEqual(await page.evaluate(()=>document.body.style.overflow),'hidden');
    await page.evaluate(()=>viewCampusPosts('校园设施与管理'));await page.locator('#postModalBody .post-item-card').first().waitFor();
    assert.equal(await page.locator('#postModalBody').evaluate(el=>el.scrollTop),0);
    await page.evaluate(()=>closePostModal());
  }
  assert.equal(errors.length,0,JSON.stringify(errors));
  fs.writeFileSync(path.join(out,'ui-results.json'),JSON.stringify({passed:true,requests:submitted.length,scriptErrors:errors,mode:'mock API; no real model result'},null,2));
  console.log('PASS: visible entry, routing, validation, all thinking modes, 429, errors, expired jobs, unknown states, degraded/missing results, report viewing, source chooser, mobile; no script errors.');
  console.log(JSON.stringify(await require('./copy_polish_checks.cjs')(page,out)));
  const crisisReview=await require('./crisis_review_checks.cjs')(page);
  fs.writeFileSync(path.join(__dirname,'crisis-review-ui-results.json'),JSON.stringify(crisisReview,null,2)+'\n');
  console.log(JSON.stringify(crisisReview));
  await browser.close();server.close();
})().catch(e=>{console.error(e);server.close();process.exit(1)});
