/* Provider presets contain public endpoints only. Secrets stay in the form or server. */
(()=>{'use strict';
const presets=[
 {id:'relay',name:'Command Code / 其他中转站',url:'',hint:'填写服务商提供的 OpenAI 兼容基础地址与模型 ID。'},
 {id:'deepseek',name:'DeepSeek 深度求索',url:'https://api.deepseek.com/v1',docs:'https://api-docs.deepseek.com/'},
 {id:'qwen',name:'阿里云百炼 · 通义千问',url:'https://dashscope.aliyuncs.com/compatible-mode/v1',docs:'https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope',hint:'预设为北京地域，其他地域或专属空间可修改地址。'},
 {id:'doubao',name:'火山方舟 · 豆包',url:'https://ark.cn-beijing.volces.com/api/v3',docs:'https://www.volcengine.com/docs/82379/1330310',hint:'模型栏填写控制台支持的模型 ID 或推理接入点 ID。'},
 {id:'glm',name:'智谱 GLM',url:'https://open.bigmodel.cn/api/paas/v4',docs:'https://docs.bigmodel.cn/cn/guide/develop/openai/introduction'},
 {id:'kimi',name:'月之暗面 Kimi',url:'https://api.moonshot.cn/v1',docs:'https://platform.moonshot.cn/docs/guide/start-using-kimi-api'},
 {id:'minimax',name:'MiniMax',url:'https://api.minimax.cn/v1',docs:'https://platform.minimax.cn/docs/api-reference/text-openai-api',aliases:['api.minimaxi.com','api.minimax.io']},
 {id:'siliconflow',name:'硅基流动 SiliconFlow',url:'https://api.siliconflow.cn/v1',docs:'https://docs.siliconflow.cn/docs/userguide/quickstart'},
 {id:'hunyuan',name:'腾讯混元',url:'https://api.hunyuan.cloud.tencent.com/v1',docs:'https://cloud.tencent.com/document/product/1729/111007'},
 {id:'qianfan',name:'百度千帆 · 文心',url:'https://qianfan.baidubce.com/v2',docs:'https://ai.baidu.com/ai-doc/WENXINWORKSHOP/0m2vwrjws'},
 {id:'spark',name:'讯飞星火',url:'https://spark-api-open.xf-yun.com/v1',docs:'https://www.xfyun.cn/doc/spark/HTTP调用文档.html',hint:'密钥栏填写该模型版本的 APIPassword；X2 等专属地址可手动修改。'}
];
const engines=[['QUERY_ENGINE','查询模型','查找事件材料'],['MEDIA_ENGINE','媒体模型','分析媒体内容'],['INSIGHT_ENGINE','洞察模型','分析讨论材料'],['REPORT_ENGINE','报告模型','事件报告、校园周报与新梗发现'],['FORUM_HOST','讨论汇总模型','整合研究观点'],['KEYWORD_OPTIMIZER','检索词优化（可选）','优化数据库检索词']];
function infer(url){try{const host=new URL(url).hostname;return presets.find(p=>p.url&&(new URL(p.url).hostname===host||(p.aliases||[]).includes(host)))?.id||'relay';}catch{return 'relay';}}
function canonical(value){try{const u=new URL(value);if(u.username||u.password||u.search||u.hash)return null;return u.origin+u.pathname.replace(/\/(?:chat\/completions|models)\/?$/,'').replace(/\/$/,'');}catch{return null;}}
function sync(root,config){root._modelSavedConfig=config;root.querySelectorAll('[data-engine]').forEach(s=>s._refreshKeyHint?.());}
function mount(root,{config,draft,api,esc}){
 root._modelSavedConfig=config;
 const c={...config,...draft};
 root.innerHTML=engines.map(([id,label,role],i)=>{
  const provider=infer(c[id+'_BASE_URL']);
  return '<details class="config-engine model-engine" data-engine="'+id+'" '+(i===3?'open':'')+'><summary><strong>'+label+'</strong><span>'+role+'</span></summary><div class="model-config-grid"><label>模型厂商<select data-provider aria-label="'+label+'厂商">'+presets.map(p=>'<option value="'+p.id+'" '+(p.id===provider?'selected':'')+'>'+p.name+'</option>').join('')+'</select></label><label>接口基础地址<input name="'+id+'_BASE_URL" type="url" value="'+esc(c[id+'_BASE_URL']||'')+'" placeholder="https://example.com/v1" autocomplete="off"></label><label>模型 ID<input name="'+id+'_MODEL_NAME" value="'+esc(c[id+'_MODEL_NAME']||'')+'" list="models-'+id+'" placeholder="填写控制台中的模型 ID" autocomplete="off"><datalist id="models-'+id+'"></datalist></label><label>API Key<input name="'+id+'_API_KEY" type="password" value="'+''+'" autocomplete="off" placeholder="'+(config[id+'_API_KEY']?'已配置，留空沿用':'填写该服务的密钥')+'"></label></div><p class="model-provider-note"></p><div class="model-connection-actions"><button type="button" data-model-action="models">读取模型列表</button><button type="button" data-model-action="test">测试连接</button><span>测试会发起一次短文本调用</span></div><p class="model-feedback" role="status" aria-live="polite"></p></details>';
 }).join('');
 root.querySelectorAll('[data-engine]').forEach(section=>{
  const id=section.dataset.engine,provider=section.querySelector('[data-provider]'),feedback=section.querySelector('.model-feedback');
  const input=suffix=>section.querySelector('[name="'+id+'_'+suffix+'"]');
  input('API_KEY').value=draft[id+'_API_KEY']||'';
  const payload=()=>({engine:id,base_url:input('BASE_URL').value.trim(),model:input('MODEL_NAME').value.trim(),api_key:input('API_KEY').value.trim()});
  function note(){const p=presets.find(p=>p.id===provider.value);section.querySelector('.model-provider-note').innerHTML=esc(p.hint||'使用 OpenAI 兼容 Chat Completions 接口，地址可编辑。')+(p.docs?' <a href="'+esc(p.docs)+'" target="_blank" rel="noopener">接口说明 ↗</a>':'');}
  section._refreshKeyHint=()=>{const saved=root._modelSavedConfig||config,base=canonical(input('BASE_URL').value),reuse=!!saved[id+'_API_KEY']&&base&&base===canonical(saved[id+'_BASE_URL']);input('API_KEY').placeholder=reuse?'已配置，留空沿用':'填写该服务的密钥';};
  function changed(){section.querySelector('datalist').innerHTML='';if(feedback.textContent){feedback.textContent='配置已修改，可重新测试';feedback.className='model-feedback';}}
  section.querySelectorAll('input[name]').forEach(el=>el.addEventListener('input',()=>{draft[el.name]=el.value;if(el===input('BASE_URL')){input('API_KEY').value='';draft[id+'_API_KEY']='';provider.value=infer(el.value);note();section._refreshKeyHint();}changed();}));
  provider.addEventListener('change',()=>{
   const p=presets.find(p=>p.id===provider.value);
   input('BASE_URL').value=p.url;input('MODEL_NAME').value='';input('API_KEY').value='';
   for(const suffix of ['BASE_URL','MODEL_NAME','API_KEY'])draft[id+'_'+suffix]=input(suffix).value;
   changed();note();section._refreshKeyHint();
  });
  note();section._refreshKeyHint();
  section.querySelectorAll('[data-model-action]').forEach(button=>button.addEventListener('click',async()=>{
   const body=payload(),signature=JSON.stringify(body),action=button.dataset.modelAction;
   if(!body.base_url){feedback.textContent='请填写接口基础地址';feedback.className='model-feedback error';return;}
   if(action==='test'&&!body.model){feedback.textContent='请填写模型 ID';feedback.className='model-feedback error';return;}
   const buttons=section.querySelectorAll('[data-model-action]');buttons.forEach(b=>b.disabled=true);
   feedback.className='model-feedback';feedback.textContent=action==='test'?'正在测试实际调用…':'正在读取模型列表…';
   try{
    const data=await api(action==='test'?'/api/test_model':'/api/fetch_models',{method:'POST',body:JSON.stringify(body)});
    if(!section.isConnected||signature!==JSON.stringify(payload()))return;
    if(action==='models'){
     const models=(data.models||[]).filter(x=>typeof x==='string').slice(0,2000);
     section.querySelector('datalist').innerHTML=models.map(m=>'<option value="'+esc(m)+'"></option>').join('');
     feedback.textContent=models.length?'已读取 '+models.length+' 个模型，可在模型 ID 栏选择或输入。':'服务商未提供模型列表，可直接填写模型 ID 后测试连接。';
    }else{feedback.textContent=data.message||'连接测试通过';}
    feedback.className='model-feedback model-success';
   }catch(error){
    if(section.isConnected&&signature===JSON.stringify(payload())){feedback.textContent=error.message+(action==='models'?'；也可直接填写模型 ID 后测试连接。':'');feedback.className='model-feedback error';}
   }finally{if(section.isConnected)buttons.forEach(b=>b.disabled=false);}
  }));
 });
}
window.CampusModelSettings={mount,sync,presets,infer};
})();
