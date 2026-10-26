const fs=require('fs'),assert=require('assert');
const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root='production/';const css=fs.readFileSync(root+'static/css/campus-review.css','utf8')+'\n'+fs.readFileSync(root+'static/css/campus-play.css','utf8');
let html=fs.readFileSync(root+'templates/index.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'').replace(/<link[^>]*rel="stylesheet"[^>]*>/g,'');html=html.replace('</head>','<style>'+css+'</style></head>');
const prefixes=['QUERY_ENGINE','MEDIA_ENGINE','INSIGHT_ENGINE','REPORT_ENGINE','FORUM_HOST','KEYWORD_OPTIMIZER'];
const config={};for(const p of prefixes){config[p+'_BASE_URL']='https://relay.example.invalid/gateway/v1';config[p+'_MODEL_NAME']='old-model';config[p+'_API_KEY']='********';}
const fixture=JSON.parse(fs.readFileSync('validation/trend-chart-fixture.json','utf8'));const theme=fixture.themes[0];
const overview={...fixture,themes:[{...theme,posts_7d:theme.posts,examples:[]}],total:theme.posts,total_7d:theme.posts,practice_count:0,observed_at:fixture.generated_at,collection_health:'fresh',coverage:theme.timeline.map(p=>({ready:p.observed})),wordcloud:[],emotion:{中性:10},window_start:fixture.generated_at-864000};
const dest='C:/Users/19946/Desktop/育人项目/分析资料/模型配置恢复预览_20261026';fs.mkdirSync(dest,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});const checks=[];
 for(const [viewport,size] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
  const page=await browser.newPage({viewport:size});const calls=[],errors=[];let saved={...config};
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());let data={success:true};
   if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:html});
   if(url.pathname==='/api/config'){
    if(req.method()==='POST'){const body=req.postDataJSON();calls.push({path:url.pathname,body});for(const [k,v] of Object.entries(body))saved[k]=k.endsWith('API_KEY')?'********':v;}
    data.config=saved;
   }else if(url.pathname==='/api/auth/me'){data={role:'admin',username:'test-admin'};}else if(url.pathname==='/api/test_model'||url.pathname==='/api/fetch_models'){
    calls.push({path:url.pathname,body:req.postDataJSON()});
    data=url.pathname==='/api/test_model'?{success:true,message:'测试成功（测试桩）'}:{success:true,models:['available-model','model-with-custom-id']};
   }else if(url.pathname==='/pulse/api/revision/overview')data={success:true,...overview};
   else if(url.pathname==='/pulse/api/campus')data={voice:{crisis:{}}};
   return route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  });
  await page.goto('https://settings.example.invalid/');
  await page.addScriptTag({content:fs.readFileSync(root+'static/js/campus-accounts.js','utf8')});
  await page.addScriptTag({content:fs.readFileSync(root+'static/js/campus-model-settings.js','utf8')});
  await page.addScriptTag({content:fs.readFileSync(root+'static/js/campus-review.js','utf8')});
  await page.locator('#configButton').click();const report=page.locator('[data-engine="REPORT_ENGINE"]');await report.waitFor({state:'visible'});
  assert.equal(await page.locator('[data-engine]').count(),6);assert.equal(await report.locator('[data-provider] option').count(),11);
  assert.equal(await report.locator('input[type=password]').inputValue(),'');
  await report.locator('[data-model-action=test]').click();await report.locator('.model-feedback').filter({hasText:'测试成功'}).waitFor();
  assert.equal(calls.at(-1).body.api_key,'');assert.equal(calls.at(-1).body.engine,'REPORT_ENGINE');
  await report.locator('input[type=password]').fill('never-reuse-this-dummy');await report.locator('[data-provider]').selectOption('deepseek');
  assert.equal(await report.locator('input[type=password]').inputValue(),'');assert.equal(await report.locator('[name=REPORT_ENGINE_MODEL_NAME]').inputValue(),'');
  assert.equal(await report.locator('[name=REPORT_ENGINE_BASE_URL]').inputValue(),'https://api.deepseek.com/v1');assert.equal(await report.locator('input[type=password]').getAttribute('placeholder'),'填写该服务的密钥');
  await report.locator('[name=REPORT_ENGINE_API_KEY]').fill('fresh-dummy-test-key');
  await report.locator('[data-model-action=models]').click();await report.locator('.model-feedback').filter({hasText:'2 个模型'}).waitFor();
  assert.equal(await report.locator('datalist option').count(),2);await report.locator('[name=REPORT_ENGINE_MODEL_NAME]').fill('available-model');
  await report.locator('[data-model-action=test]').click();await report.locator('.model-feedback').filter({hasText:'测试成功'}).waitFor();
  assert.equal(calls.at(-1).body.api_key,'fresh-dummy-test-key');assert.equal(calls.at(-1).body.model,'available-model');
  await page.locator('[data-service=search]').click();await page.locator('[data-service=llm]').click();
  assert.equal(await report.locator('[name=REPORT_ENGINE_MODEL_NAME]').inputValue(),'available-model');assert.equal(await report.locator('input[type=password]').inputValue(),'fresh-dummy-test-key');
  await report.locator('[data-provider]').selectOption('relay');await report.locator('[name=REPORT_ENGINE_BASE_URL]').fill('https://new-relay.example.invalid/custom/v1');
  await report.locator('[name=REPORT_ENGINE_MODEL_NAME]').fill('proxy-model');await report.locator('[name=REPORT_ENGINE_API_KEY]').fill('relay-dummy');
  await report.locator('[data-model-action=test]').click();await report.locator('.model-feedback').filter({hasText:'测试成功'}).waitFor();
  assert.equal(calls.at(-1).body.base_url,'https://new-relay.example.invalid/custom/v1');
  assert(!calls.some(c=>c.path==='/api/config'));
  await page.locator('#configForm button.primary').click();await page.locator('#configStatus').filter({hasText:'已保存'}).waitFor();
  const save=calls.find(c=>c.path==='/api/config');assert.equal(save.body.REPORT_ENGINE_API_KEY,'relay-dummy');assert(!('QUERY_ENGINE_API_KEY' in save.body));
  assert.equal(await report.locator('input[type=password]').inputValue(),'');assert.equal(await report.locator('input[type=password]').getAttribute('placeholder'),'已配置，留空沿用');assert(! (await page.locator('#configFields').innerHTML()).includes('fresh-dummy-test-key'));
  assert.equal(await page.locator('.model-engine[open]').count(),1);
  const overflow=await page.locator('#configDialog').evaluate(el=>el.scrollWidth>el.clientWidth);assert(!overflow);
  assert.deepEqual(errors,[]);await report.locator('[data-provider]').scrollIntoViewIfNeeded();await page.screenshot({path:dest+'/'+viewport+'.png'});
  checks.push({viewport,engines:6,domestic_presets:10,relay_custom_path:true,stored_key_not_exposed:true,preset_change_clears_key:true,draft_survives_tabs:true,models_and_actual_test_actions:true,test_does_not_save:true,save_does_not_overwrite_blank_keys:true,overflow:false});await page.close();
 }
 await browser.close();fs.writeFileSync('validation/model-settings-browser-results.json',JSON.stringify({passed:true,checks},null,2)+'\n');console.log(JSON.stringify({passed:true,checks,previews:dest}));
})().catch(e=>{console.error(e);process.exit(1)});
