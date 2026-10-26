(()=>{'use strict';
 function extract(){
  const here=new URL(location.href),allowed=new Set(['www.xiaohongshu.com','xiaohongshu.com']);
  if(here.protocol!=='https:'||!allowed.has(here.hostname)||here.pathname.replace(/\/$/,'')!=='/search_result')throw Error('请先在小红书打开“华理”的搜索结果页');
  const school=text=>/华东理工|华理|ECUST/i.test(text)&&(/华东理工|ECUST/i.test(text)||!/华北理工|东华理工|华南理工|华中科技/.test(text));
  const keyword=here.searchParams.get('keyword')||'';
  if(!school(keyword))throw Error('请先搜索“华理”或“华东理工大学”');
  function identity(href){
   try{const u=new URL(href,location.origin);if(u.protocol!=='https:'||!allowed.has(u.hostname)||u.username||u.password||(u.port&&u.port!=='443'))return null;
    const match=u.pathname.match(/^\/(?:explore|search_result|discovery\/item)\/([a-fA-F0-9]{24})\/?$/);if(!match)return null;
    const link=new URL('https://www.xiaohongshu.com/explore/'+match[1].toLowerCase());
    for(const k of ['xsec_token','xsec_source','source']){const value=u.searchParams.get(k);if(value&&value.length<=1024)link.searchParams.set(k,value);}
    return {id:match[1].toLowerCase(),url:link.href};
   }catch{return null;}
  }
  function titleOf(card,anchor){
   const title=card.querySelector('a.title,.note-title,[data-testid="note-title"],.title');
   return (title?.innerText||anchor.getAttribute('title')||anchor.innerText||card.querySelector('img[alt]')?.getAttribute('alt')||'').replace(/\s+/g,' ').trim().slice(0,240);
  }
  const found=new Map();let inspected=0;
  for(const a of document.querySelectorAll('a[href]')){
   const note=identity(a.href);if(!note)continue;
   const style=getComputedStyle(a),rect=a.getBoundingClientRect();if(style.display==='none'||style.visibility==='hidden'||(!rect.width&&!rect.height))continue;
   inspected++;let card=a.closest('section.note-item,article,[data-note-id],.note-item,.note-card'),title='';
   if(card)title=titleOf(card,a);
   else{card=a;for(let depth=0;depth<5&&card;depth++,card=card.parentElement){
     const ids=new Set([...card.querySelectorAll('a[href]')].map(x=>identity(x.href)?.id).filter(Boolean));
     if(ids.size>1){card=null;break;}
     title=titleOf(card,a);if(title)break;
   }}
   if(!card||!title)continue;
   const excerpt=(card.querySelector('.note-desc,.desc,[data-testid="note-description"]')?.innerText||'').replace(/\s+/g,' ').trim().slice(0,1000);
   if(!school(title+' '+excerpt))continue;
   if(!found.has(note.id))found.set(note.id,{url:note.url,title,excerpt});
   if(found.size>=30)break;
  }
  if(!found.size)throw Error(inspected?'已读到笔记链接，但卡片上暂无明确的华理文字线索；可换一个关键词或等待结果加载':'暂未读到笔记卡片，请完成登录并等待搜索结果加载');
  return {format:'ecust-xhs-visible-v1',captured_at:Math.floor(Date.now()/1000),page_url:'https://www.xiaohongshu.com/search_result?keyword='+encodeURIComponent(keyword),items:[...found.values()]};
 }
 globalThis.EcustXhsCollector={extract};
})();
