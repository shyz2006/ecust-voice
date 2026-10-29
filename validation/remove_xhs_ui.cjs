const fs=require('fs'),assert=require('assert');
const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root='production/';const css=fs.readFileSync(root+'static/css/campus-review.css','utf8')+'\n'+fs.readFileSync(root+'static/css/campus-play.css','utf8');
let html=fs.readFileSync(root+'templates/index.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'').replace(/<link[^>]*rel="stylesheet"[^>]*>/g,'');html=html.replace('</head>','<style>'+css+'</style></head>');
const fixture=JSON.parse(fs.readFileSync('validation/trend-chart-fixture.json','utf8'));const theme=fixture.themes[0];
const overview={...fixture,themes:[{...theme,posts_7d:theme.posts,examples:[]}],total:theme.posts,total_7d:theme.posts,practice_count:0,observed_at:fixture.generated_at,collection_health:'fresh',coverage:theme.timeline.map(p=>({ready:p.observed})),wordcloud:[],emotion:{中性:10},window_start:fixture.generated_at-864000};
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});const checks=[];
 for(const [name,size] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
  const page=await browser.newPage({viewport:size});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{const url=new URL(route.request().url());let data={success:true};
   if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:html});
   if(url.pathname==='/api/auth/me')data={role:'admin',username:'test-admin'};
   else if(url.pathname==='/pulse/api/revision/overview')data={success:true,...overview};
   else if(url.pathname==='/pulse/api/campus')data={voice:{crisis:{}}};
   else if(url.pathname==='/pulse/api/revision/ledger')data={sources:[{source:'huyou-school',unique:12},{source:'ecust-news',unique:3},{source:'douyin',unique:10}],unique_items:25,unique_school_posts:12,reports_completed:0,daily_usage:[]};
   else if(url.pathname.includes('/feed/hot'))data={platforms:['抖音','B站'],items:[],candidate_counts:{}};
   else if(url.pathname.includes('/official-news'))data={items:[],total:0,window_days:180,status:'waiting'};
   return route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  });
  await page.goto('https://removal.example.invalid/');
  await page.addScriptTag({content:fs.readFileSync(root+'static/js/campus-review.js','utf8')});
  await page.locator('[data-tab="hot"]').click();await page.locator('#hotPlatforms button').first().waitFor();
  assert.equal(await page.locator('#hotPlatforms button').count(),2);
  await page.locator('[data-tab="ledger"]').click();await page.locator('#sourceBars [data-source="ecust-news"]').waitFor();
  assert(!(await page.locator('body').innerText()).includes('小红书'));
  assert.equal(await page.locator('[data-source="xiaohongshu-school"]').count(),0);
  assert.equal(await page.locator('script[src*="xhs"], [id*="xhs"], [id="hotScope"]').count(),0);
  assert.deepEqual(errors,[]);checks.push({viewport:name,passed:true});await page.close();
 }
 await browser.close();fs.writeFileSync('validation/remove-xhs-ui-results.json',JSON.stringify({passed:true,checks},null,2)+'\n');console.log(JSON.stringify({passed:true,checks}));
})().catch(e=>{console.error(e);process.exit(1)});
