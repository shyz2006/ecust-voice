const fs=require('fs'),assert=require('assert');
const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const collector=fs.readFileSync('browser-tools/xhs-visible/collector.js','utf8');
const root='production/',dest='C:/Users/19946/Desktop/育人项目/分析资料/小红书本机同步预览_20261026';fs.mkdirSync(dest,{recursive:true});
const note=(id,title,other='')=>`<section class="note-item" ${other}><a class="cover" href="/search_result/${id}?xsec_token=note-link&tracking=discard"><img alt="${title}" width="50" height="50"></a><a class="title" href="/explore/${id}">${title}</a><div class="author">DO-NOT-EXPORT-AUTHOR</div></section>`;
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page=await browser.newPage();let markup=note('a'.repeat(24),'华理奉贤食堂')+note('a'.repeat(24),'华理重复卡片')+note('b'.repeat(24),'无关学校穿搭')+note('c'.repeat(24),'华理隐藏卡片','style="display:none"');
 await page.route('**/*',r=>r.fulfill({contentType:'text/html; charset=utf-8',body:markup}));
 await page.goto('https://www.xiaohongshu.com/search_result?keyword=%E5%8D%8E%E7%90%86');
 await page.addScriptTag({content:collector});
 const data=await page.evaluate(()=>{localStorage.setItem('private-session','DO-NOT-EXPORT-SECRET');return EcustXhsCollector.extract();});
 assert.equal(data.items.length,1);assert(data.items[0].url.includes('/explore/'));assert(!data.items[0].url.includes('tracking'));
 assert(!JSON.stringify(data).includes('DO-NOT-EXPORT'));assert.deepEqual(Object.keys(data).sort(),['captured_at','format','items','page_url']);
 markup=Array.from({length:35},(_,i)=>note(i.toString(16).padStart(24,'0'),'华理校园 '+i)).join('');
 await page.reload();await page.addScriptTag({content:collector});assert.equal((await page.evaluate(()=>EcustXhsCollector.extract())).items.length,30);
 await page.goto('https://www.xiaohongshu.com/explore');await page.addScriptTag({content:collector});await assert.rejects(()=>page.evaluate(()=>EcustXhsCollector.extract()),/搜索结果页/);
 await page.close();
 let html=fs.readFileSync(root+'templates/index.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'').replace(/<link[^>]*rel="stylesheet"[^>]*>/g,'');
 const css=['campus-review','campus-play'].map(n=>fs.readFileSync(root+'static/css/'+n+'.css','utf8')).join('\n');html=html.replace('</head>','<style>'+css+'</style></head>');
 const checks=[];
 for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
  const p=await browser.newPage({viewport}),errors=[],imports=[];p.on('pageerror',e=>errors.push(e.message));
  await p.route('**/*',route=>{const u=new URL(route.request().url());if(u.pathname==='/')return route.fulfill({contentType:'text/html; charset=utf-8',body:html});let out={success:true};if(u.pathname.endsWith('/key'))out={success:true,token:'ecust_xhs_test-fixture',expires_at:1900000000};
   if(u.pathname==='/pulse/api/xhs-browser/status')out={success:true,stored:0,refresh:{state:'idle'}};
   if(u.pathname==='/pulse/api/xhs-browser/import'){imports.push(route.request().postDataJSON());out={success:true,received:1,added:1,updated:0,rejected:0};}
   return route.fulfill({contentType:'application/json',body:JSON.stringify(out)});
  });
  await p.goto('https://portal.example.invalid/');await p.addScriptTag({content:fs.readFileSync(root+'static/js/campus-xhs-sync.js','utf8')});
  await p.evaluate(()=>{document.getElementById('configDialog').showModal();document.getElementById('configForm').hidden=true;document.querySelectorAll('[data-service]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.service==='search')));CampusXhsSync.toggle(true);document.querySelector('#xhsBrowserPane details').open=true;});
  await p.locator('#xhsImportFile').setInputFiles({name:'visible-notes.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(data))});
  await p.locator('#xhsImportSubmit').waitFor({state:'visible'});assert((await p.locator('#xhsImportPreview').textContent()).includes('华理奉贤食堂'));
  await p.locator('#xhsImportSubmit').click();await p.locator('#xhsImportMessage').filter({hasText:'已接收 1 条'}).waitFor();assert.equal(imports.length,1);
  await p.locator('#xhsPairCreate').click();await p.locator('#xhsPairValue').waitFor({state:'visible'});assert.equal(await p.locator('#xhsPairToken').inputValue(),'ecust_xhs_test-fixture');await p.locator('#xhsPairRevoke').click();await p.locator('#xhsPairValue').waitFor({state:'hidden'});
  await p.locator('#xhsImportFile').setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from('{}')});assert(await p.locator('#xhsImportSubmit').isHidden());
  await p.screenshot({path:dest+'/'+name+'.png',fullPage:true});assert.deepEqual(errors,[]);checks.push({viewport:name,preview_import_and_reject:true});await p.close();
 }
 await browser.close();
 const result={passed:true,fixture_only:true,real_user_capture_verified:false,collector_dedup_school_filter_hidden_filter_and_cap:true,account_state_not_exported:true,checks};
 fs.writeFileSync('validation/xhs-browser-ui-results.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
})().catch(e=>{console.error(e);process.exit(1);});
