(()=>{'use strict';
 const HOSTS=new Set(['www.xiaohongshu.com','xiaohongshu.com']);
 const CARD='section.note-item,article,[data-note-id],.note-item,.note-card';
 const TITLE='a.title,.title,.note-title,[data-testid="note-title"],[class*="note-title"],[class*="noteTitle"],[class*="title-text"],[class*="titleText"],h2,h3';
 const META='.author,.author-wrapper,.user-info,[class*="author"],[class*="Author"],[href*="/user/profile/"],.like-wrapper,.count,time';
 const school=text=>/华东理工|华理|ECUST/i.test(text)&&(/华东理工|ECUST/i.test(text)||!/华北理工|东华理工|华南理工|华中科技/.test(text));
 const normalize=text=>String(text||'').replace(/\s+/g,' ').trim();
 function context(){const here=new URL(location.href);if(here.protocol!=='https:'||!HOSTS.has(here.hostname)||here.pathname.replace(/\/$/,'')!=='/search_result')throw Error('请先在小红书打开“华理”的搜索结果页');const keyword=here.searchParams.get('keyword')||'';if(!school(keyword))throw Error('请先搜索“华理”或“华东理工大学”');return keyword;}
 function identity(href){try{const u=new URL(href,location.origin);if(u.protocol!=='https:'||!HOSTS.has(u.hostname)||u.username||u.password||(u.port&&u.port!=='443'))return null;const match=u.pathname.match(/^\/(?:explore|search_result|discovery\/item)\/([a-fA-F0-9]{24})\/?$/);if(!match)return null;const link=new URL('https://www.xiaohongshu.com/explore/'+match[1].toLowerCase());for(const k of ['xsec_token','xsec_source','source']){const value=u.searchParams.get(k);if(value&&value.length<=1024)link.searchParams.set(k,value);}return {id:match[1].toLowerCase(),url:link.href};}catch{return null;}}
 function hidden(el){for(let p=el;p&&p!==document.documentElement;p=p.parentElement){const style=getComputedStyle(p);if(style.display==='none'||style.visibility==='hidden'||style.visibility==='collapse'||style.contentVisibility==='hidden')return true;}return false;}
 function rendered(el){const r=el.getBoundingClientRect();return !hidden(el)&&(r.width>0||r.height>0);}
 function text(el){if(!el||hidden(el))return '';const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);let out='',node;while((node=walker.nextNode())){if(!hidden(node.parentElement))out+=' '+node.textContent;}return normalize(out);}
 function titleOf(card,anchor){
  for(const el of card.querySelectorAll(TITLE)){if(el.closest(META))continue;const value=text(el);if(value)return value.slice(0,240);}
  // Some layouts render the title as a plain footer label. Keep author/counter nodes out.
  const candidates=card.querySelectorAll('.footer,.card-footer,[class*="note-content"],[class*="noteContent"]');
  for(const box of candidates){const leaves=[...box.querySelectorAll('a,span,p,div')].filter(el=>!el.children.length&&!el.closest(META));for(const el of leaves){const value=text(el);if(school(value))return value.slice(0,240);}}
  const own=normalize(anchor.getAttribute('title')||text(anchor));if(own&&school(own))return own.slice(0,240);
  const alt=normalize(card.querySelector('img[alt]')?.getAttribute('alt'));return school(alt)?alt.slice(0,240):'';
 }
 function scan(){
  const keyword=context(),found=new Map(),visited=new Set();
  const diagnostics={links:0,cards:0,titles:0,school_matches:0,visibility:document.visibilityState};
  const anchors=[...document.querySelectorAll('a[href]')].map(a=>({a,note:identity(a.getAttribute('href'))})).filter(x=>x.note);diagnostics.links=anchors.length;
  for(const {a,note} of anchors){
   if(hidden(a.parentElement))continue;
   let card=a.closest(CARD),title='';
   const idsOf=box=>new Set([...(box.matches('a[href]')?[box]:[]),...box.querySelectorAll('a[href]')].map(x=>identity(x.getAttribute('href'))?.id).filter(Boolean));
   if(card&&idsOf(card).size===1&&rendered(card))title=titleOf(card,a);else card=null;
   if(!title){let best=null;for(let parent=a.parentElement,depth=0;parent&&depth<9;parent=parent.parentElement,depth++){
     if(parent.matches('body,html,main'))break;const ids=idsOf(parent);if(ids.size>1)break;if(!rendered(parent))continue;
     const candidate=titleOf(parent,a);if(candidate){best={card:parent,title:candidate};if(parent.matches(CARD)||parent.querySelector(TITLE))break;}
    }if(best){card=best.card;title=best.title;}}
   if(!card||!rendered(card))continue;
   if(!visited.has(card)){diagnostics.cards++;if(title)diagnostics.titles++;visited.add(card);}
   if(!title)continue;
   const excerpt=text(card.querySelector('.note-desc,.desc,[data-testid="note-description"]')).slice(0,1000);
   if(!school(title+' '+excerpt))continue;
   const previous=found.get(note.id);if(!previous){diagnostics.school_matches++;found.set(note.id,{url:note.url,title,excerpt});}
   else if(!previous.url.includes('xsec_token=')&&note.url.includes('xsec_token='))previous.url=note.url;
  }
  return {diagnostics,data:{format:'ecust-xhs-visible-v1',captured_at:Math.floor(Date.now()/1000),page_url:'https://www.xiaohongshu.com/search_result?keyword='+encodeURIComponent(keyword),items:[...found.values()].slice(0,30)}};
 }
 function extract(){const result=scan();if(!result.data.items.length){const d=result.diagnostics,error=Error('读取到 '+d.links+' 个笔记链接、'+d.titles+' 张有标题的卡片，华理匹配 '+d.school_matches+' 条；请等待页面加载或检查卡片结构');error.diagnostics=d;throw error;}return result.data;}
 globalThis.EcustXhsCollector={extract,inspect:()=>scan().diagnostics};
})();
