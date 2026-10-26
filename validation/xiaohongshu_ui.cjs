const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('production/static/js/campus-review.js','utf8');
const load=src.slice(src.indexOf('async function loadFeed('),src.indexOf('function signalPill('));
const render=src.slice(src.indexOf('function renderPosts('),src.indexOf('async function openPosts('));
const elements={},$=id=>elements[id]||(elements[id]={innerHTML:''});
const rows=Array.from({length:20},(_,i)=>({source:'xiaohongshu',platform:'小红书',title:'话题'+i,ts:1,focus:'焦点'+i,url:'https://www.xiaohongshu.com/search_result?keyword='+i,link_kind:'platform_search'}));
const ctx={state:{hotPlatform:'小红书'},$,api:async()=>({platforms:['B站','小红书'],items:rows,candidate_counts:{小红书:20}}),esc:String,date:()=>'',signalPill:()=>'',sourceLink:(url,label)=>'<a href="'+url+'">'+label+'</a>',sourceSearchUrl:()=>'',empty:String,NAMES:{xiaohongshu:'小红书'},num:String};
(async()=>{
 await vm.runInNewContext(load+';loadFeed("hot",true)',ctx);
 assert.equal((elements.hotFeed.innerHTML.match(/class="feed-card"/g)||[]).length,10);
 assert.equal((elements.hotFeed.innerHTML.match(/在平台搜索话题/g)||[]).length,10);
 assert(!elements.hotFeed.innerHTML.includes('打开原帖'));
 assert(elements.hotScope.textContent.includes('20 个话题'));assert(!elements.hotScope.hidden);
 const post=vm.runInNewContext(render+';renderPosts(state.hot.items.slice(0,1))',ctx);
 assert(post.includes('在平台搜索话题'));assert(!post.includes('打开原帖'));
 for(const path of ['production/templates/index.html','production/CampusPulse/templates/pulse.html'])assert(fs.readFileSync(path,'utf8').includes('campus-review.js?v=20261026m2'));
 const result={passed:true,hot_cards:10,platform_search_labels:true,source_dialog_search_label:true,templates_updated:2};
 fs.writeFileSync('validation/xiaohongshu-ui-results.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
})().catch(e=>{console.error(e);process.exit(1)});
