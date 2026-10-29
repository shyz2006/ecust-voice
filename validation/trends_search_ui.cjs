const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('production/static/js/campus-review.js','utf8');
const helpers=src.slice(src.indexOf('function metric('),src.indexOf('function showDialog('));
const full=src.slice(src.indexOf('function fullChart('),src.indexOf('async function openTrend('));
const DAY=86400,ts=1792000000,series=Array.from({length:10},(_,i)=>({ts:ts+i*DAY,observed:i<8,new_posts:i<8?i+1:null,posts:i<8?i+1:3}));
const theme={theme:'学业课程',color:'#aa88cc',posts:40,posts_24h:3,delta:null,timeline:series,reference:{value:4,lower:0,upper:8,windows:8,lag_windows:2},comparison:{value:1,basis:'latest_complete',current:8,previous:7,start:series[7].ts,end:series[7].ts+DAY}};
const elements={},$=id=>elements[id]||(elements[id]={innerHTML:'',textContent:'',hidden:false});
const context={state:{overview:{themes:[theme,{...theme,theme:'零值议题',reference:{value:0,windows:8,lag_windows:2},comparison:{value:0,basis:'current'}}],total:40,coverage:series.map(p=>({ready:p.observed})),window_start:ts,generated_at:ts+10*DAY,wordcloud:[]}},$,num:String,esc:String,shortDate:v=>new Date(v*1000).toISOString().slice(5,10),empty:String,DAY};
vm.runInNewContext(helpers+';renderTrends()',context);
assert(elements.trendRows.innerHTML.includes('最近完整窗'));
assert(elements.trendStatus.textContent.includes('虚线为预估'));
assert(!elements.trendStatus.hidden);
assert(elements.trendRows.innerHTML.includes('约 0 篇'));
assert(!elements.trendRows.innerHTML.includes('待完整采集'));
const svg=vm.runInNewContext(full+';fullChart(state.overview.themes[0])',context);
assert(svg.includes('class="trend-reference-card"'));assert(svg.includes('次日参考'));assert(!svg.includes('reference-projection'));
assert(svg.includes('参考范围'));assert(!svg.includes('class="collection-gap"'));assert(svg.includes('class="estimated-point"'));assert(!svg.includes('已采集 3 篇'));
 const detail=vm.runInNewContext('trendDetail(state.overview.themes[0])',context);assert(detail.includes('同期已收录原帖'));assert(detail.includes('统计与参考依据'));
assert(!/NaN|undefined/.test(svg));
context.state.overview.coverage.forEach(c=>c.ready=true);vm.runInNewContext('renderTrends()',context);assert(!elements.trendStatus.hidden);context.state.overview.themes.forEach(t=>t.timeline.forEach(p=>p.new_posts=p.posts));vm.runInNewContext('renderTrends()',context);assert(elements.trendStatus.hidden);
for(const path of ['production/templates/index.html','production/CampusPulse/templates/pulse.html']){
 const html=fs.readFileSync(path,'utf8');assert(html.includes('id="trendStatus"'));assert(html.includes('campus-review.js?v=20261029r1'));
}
const result={passed:true,dated_fallback_comparison:true,partial_collection_notice:true,zero_reference_visible:true,separate_reference_card_and_range:true,gap_counts_not_filled_as_complete:true,templates_updated:2};
fs.writeFileSync('validation/trends-search-ui-results.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
