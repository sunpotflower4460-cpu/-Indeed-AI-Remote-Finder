(()=>{
  'use strict';

  const PLUGIN_SRC='https://plugins.indeed.com/publisher-plugin/main.js';
  const config=window.INDEED_PARTNER_CONFIG||{};

  function configured(){
    return Boolean(String(config.partnerAppId||'').trim()&&String(config.placementId||'').trim());
  }

  function ensureSection(){
    let section=document.querySelector('#indeedOfficialSearch');
    if(section)return section;
    const tabs=document.querySelector('#uxSourceTabs');
    if(!tabs)return null;
    section=document.createElement('section');
    section.id='indeedOfficialSearch';
    section.className='indeedOfficialSearch uxHidden';
    section.innerHTML='<div class="indeedOfficialHead"><b>Indeed公式検索</b><span>Indeed / Indeed PLUS の検索結果</span></div><div id="indeedPublisherRoot"></div><div id="indeedPluginStatus" class="indeedPluginStatus"></div>';
    tabs.insertAdjacentElement('afterend',section);
    return section;
  }

  function buildRoot(section){
    const root=section?.querySelector('#indeedPublisherRoot');
    if(!root||root.dataset.ready==='1')return root;
    root.dataset.indeedPluginType='job-search';
    root.dataset.indeedPartnerAppId=String(config.partnerAppId||'').trim();
    root.dataset.indeedPlacementId=String(config.placementId||'').trim();
    root.dataset.indeedSearchLimit=String(Math.max(1,Math.min(20,Number(config.searchLimit)||10)));
    if(String(config.searchWhat||'').trim())root.dataset.indeedSearchWhat=String(config.searchWhat).trim();
    if(String(config.searchWhere||'').trim())root.dataset.indeedSearchWhere=String(config.searchWhere).trim();
    root.dataset.ready='1';
    root.addEventListener('indeed-plugin-event',event=>{
      const detail=event?.detail||{};
      if(detail.type!=='load')return;
      const status=section.querySelector('#indeedPluginStatus');
      if(!status)return;
      status.textContent=detail.payload?.success===true?'Indeed公式検索を読み込みました。':'Indeed公式検索を読み込めませんでした。下の確認済み候補は引き続き利用できます。';
    });
    return root;
  }

  function loadPlugin(){
    if(document.querySelector(`script[src="${PLUGIN_SRC}"]`))return;
    const script=document.createElement('script');
    script.src=PLUGIN_SRC;
    script.crossOrigin='anonymous';
    script.defer=true;
    document.head.appendChild(script);
  }

  function sync(){
    const section=ensureSection();
    if(!section)return;
    const indeedMode=window.__jobSourceTabs?.mode!=='other';
    section.classList.toggle('uxHidden',!configured()||!indeedMode);
    if(!configured()||!indeedMode)return;
    buildRoot(section);
    loadPlugin();
  }

  const style=document.createElement('style');
  style.textContent='.indeedOfficialSearch{margin-top:10px;border:1px solid #24465f;border-radius:14px;background:#071522;padding:12px;overflow:hidden}.indeedOfficialHead{display:flex;flex-direction:column;gap:2px;margin-bottom:10px}.indeedOfficialHead b{font-size:13px;color:#e8f8ff}.indeedOfficialHead span,.indeedPluginStatus{font-size:9px;color:#7f9bb0;line-height:1.5}.indeedPluginStatus{margin-top:8px}';
  document.head.appendChild(style);

  const previousRender=render;
  render=function(){previousRender();sync();};
  sync();

  window.__indeedOfficial={configured,sync};
})();
