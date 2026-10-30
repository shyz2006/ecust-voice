// Compatibility fixtures for rendered cards, not a capture of the user's live page.
const fs=require('fs'),assert=require('assert'),cp=require('child_process');
const {chromium}=require('C:/Users/19946/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const current=fs.readFileSync('browser-tools/xhs-visible/collector.js','utf8');
const previous=cp.execFileSync('git',['show','ca1169f:browser-tools/xhs-visible/collector.js'],{encoding:'utf8'});
const id='a'.repeat(24),id2='b'.repeat(24),url='/search_result/'+id+'?xsec_token=fixture-link';
const fixtures=[
 {name:'hidden_identity_link_visible_title',body:`<section class="note-item"><a href="${url}" style="display:none"></a><div style="height:100px">封面</div><div class="title">华理，可以改名叫野区了</div></section>`,expected:1,oldFails:true},
 {name:'generic_wrapper_cover_alt_not_title',body:`<div class="tile"><a href="${url}"><img width="100" height="100" alt="cover"></a><div class="footer"><a class="title">华理徐汇食堂一日记录</a><div class="author">DO-NOT-EXPORT-AUTHOR</div></div></div>`,expected:1,oldFails:true},
 {name:'feed_article_not_one_card',body:`<article><div class="tile"><a href="${url}"><img width="100" height="100" alt="cover"></a><span class="title">华理校园</span></div><div class="tile"><a href="/explore/${id2}"><img width="100" height="100" alt="cover"></a><span class="title">其他大学</span></div></article>`,expected:1},
 {name:'hidden_card_cannot_borrow_page_title',body:`<h2>华理搜索</h2><section class="note-item" style="display:none"><a href="${url}">华理隐藏卡片</a></section>`,expected:0},
 {name:'diagnostic_counts_are_retained',body:`<section class="note-item"><a href="${url}">cover</a><div class="title">普通购物</div></section>`,expected:0,diagnostics:true}
];
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});let body='';const page=await browser.newPage();await page.route('**/*',r=>r.fulfill({contentType:'text/html; charset=utf-8',body:'<!doctype html><meta charset="utf-8">'+body}));const checks=[];
 try{for(const fixture of fixtures){body=fixture.body;await page.goto('https://www.xiaohongshu.com/search_result?keyword=%E5%8D%8E%E7%90%86&type=51');await page.addScriptTag({content:current});const result=await page.evaluate(()=>{try{return {items:EcustXhsCollector.extract().items};}catch(e){return {items:[],diagnostics:e.diagnostics};}});assert.equal(result.items.length,fixture.expected,fixture.name);assert(!JSON.stringify(result).includes('DO-NOT-EXPORT'));
  if(fixture.diagnostics){assert.equal(result.diagnostics.links,1);assert.equal(result.diagnostics.titles,1);assert.equal(result.diagnostics.school_matches,0);}
  if(fixture.oldFails){await page.addScriptTag({content:previous});assert(await page.evaluate(()=>{try{EcustXhsCollector.extract();return false;}catch{return true;}}),'old failure reproduced');}
  checks.push({name:fixture.name,passed:true,old_failure_reproduced:!!fixture.oldFails});
 }const proof={passed:true,fixture_only:true,real_user_page_verified:false,checks};fs.writeFileSync('validation/xhs-card-compatibility-results.json',JSON.stringify(proof,null,2)+'\n');console.log(JSON.stringify(proof));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
