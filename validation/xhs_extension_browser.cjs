// Load the reviewed extension into a disposable test profile, with both websites mocked.
const fs=require('fs'),os=require('os'),path=require('path'),assert=require('assert');
const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const extension=path.resolve('browser-tools/xhs-visible'),profile=fs.mkdtempSync(path.join(os.tmpdir(),'ecust-xhs-extension-test-'));
 const context=await chromium.launchPersistentContext(profile,{executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true,args:['--disable-extensions-except='+extension,'--load-extension='+extension],viewport:{width:600,height:800}});
 try{
  const uploaded=[];
  await context.route('https://smydashuaige.2026515.xyz/**',async r=>{const isPush=r.request().url().endsWith('/push');if(isPush)uploaded.push(r.request().postDataJSON());return r.fulfill({contentType:'application/json',body:JSON.stringify({success:true,received:1,added:1})});});
  await context.route('https://www.xiaohongshu.com/**',r=>r.fulfill({contentType:'text/html; charset=utf-8',body:'<!doctype html><meta charset="utf-8"><section class="note-item"><a class="cover" href="/search_result/aaaaaaaaaaaaaaaaaaaaaaaa?xsec_token=fixture-link"><img width="100" height="100" alt="华理校园测试卡片"></a><a class="title" href="/explore/aaaaaaaaaaaaaaaaaaaaaaaa">华理校园测试卡片</a></section>'}));
  let worker=context.serviceWorkers()[0]||await context.waitForEvent('serviceworker',{timeout:15000});
  const id=new URL(worker.url()).host,popup=await context.newPage();await popup.goto('chrome-extension://'+id+'/popup.html');
  await popup.locator('#token').fill('ecust_xhs_'+'a'.repeat(43));await popup.locator('#connect').click();
  await popup.locator('#autoStatus').filter({hasText:'已同步 1 条'}).waitFor({timeout:35000});
  assert.equal(uploaded.length,1);assert.equal(uploaded[0].items[0].title,'华理校园测试卡片');assert.equal(uploaded[0].items[0].excerpt,'');
  const status=await worker.evaluate(()=>chrome.storage.local.get(['enabled','last']));assert(status.enabled);assert.equal(status.last.state,'complete');
  await popup.locator('#pause').click();await popup.locator('#autoStatus').filter({hasText:'自动同步未运行'}).waitFor();
  await popup.screenshot({path:'C:/Users/19946/Desktop/育人项目/分析资料/小红书本机同步预览_20261026/extension.png'});
  const result={passed:true,disposable_profile:true,fixture_only:true,extension_manifest_loaded:true,real_extension_injection_and_upload:true,real_user_capture_verified:false};
  fs.writeFileSync('validation/xhs-extension-browser-results.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
 }finally{await context.close();}
})().catch(e=>{console.error(e);process.exit(1);});
