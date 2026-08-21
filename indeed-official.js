(()=>{
  'use strict';

  const PLUGIN_SRC='https://plugins.indeed.com/publisher-plugin/main.js';
  const config=window.INDEED_PARTNER_CONFIG||{};
  const DEFAULT_QUERY='AI 在宅';
  const REMOTE_RE=/(在宅|リモート|remote|work\s*from\s*home|wfh)/i;
  const PRESETS=[
    ['広く探す','AI 在宅'],
    ['AIトレーナー','AIトレーナー 在宅'],
    ['レイター','rater remote'],
    ['AI評価','AI評価 在宅'],
    ['アノテーション','アノテーション 在宅'],
    ['データラベリング','データラベリング 在宅'],
    ['翻訳','翻訳 在宅'],
    ['校正','校正 在宅'],
    ['文字起こし','文字起こし 在宅'],
    ['検索品質','search quality remote']
  ];

  function configured(){
    return Boolean(String(config.partnerAppId||'').trim()&&String(config.placementId||'').trim());
  }

  function safeIndeedViewjob(value){
    try{
      const url=new URL(String(value||''));
      const host=url.hostname.toLowerCase();
      if(url.protocol!=='https:')return null;
      if(!(host==='indeed.com'||host.endsWith('.indeed.com')))return null;
      if(url.pathname.toLowerCase()!=='/viewjob')return null;
      if(!url.searchParams.get('jk'))return null;
      return url;
    }catch{return null;}
  }

  function normalizeIndeedQuery(query){
    const typed=String(query||'').replace(/\s+/g,' ').trim()||DEFAULT_QUERY;
    return REMOTE_RE.test(typed)?typed:`${typed} 在宅`;
  }

  function buildIndeedSearchUrl(query){
    const url=new URL('https://jp.indeed.com/jobs');
    // Indeed Japan commonly accepts nationwide remote intent in the q field.
    // Do not use l=在宅: treating "在宅" as a location can over-constrain results.
    url.searchParams.set('q',normalizeIndeedQuery(query));
    url.searchParams.set('sort','date');
    return url.toString();
  }

  function openIndeed(query){
    window.open(buildIndeedSearchUrl(query),'_blank','noopener');
  }

  function ageLabel(value){
    const time=Date.parse(String(value||''));
    if(!Number.isFinite(time))return'確認日時不明';
    const days=Math.max(0,Math.floor((Date.now()-time)/864e5));
    if(days===0)return'24時間以内にURL確認';
    return`${days}日前にURL確認`;
  }

  function ensureSection(){
    let section=document.querySelector('#indeedOfficialSearch');
    if(section)return section;
    const tabs=document.querySelector('#uxSourceTabs');
    if(!tabs)return null;
    section=document.createElement('section');
    section.id='indeedOfficialSearch';
    section.className='indeedOfficialSearch';
    section.innerHTML=`
      <div class="indeedOfficialHead">
        <b>Indeed本体から探す</b>
        <span>Indeedの現在の検索結果を直接開きます。アプリが自動取得した候補とは別に、まず本体側の求人を確認できます。</span>
      </div>
      <div id="indeedTruthBar" class="indeedTruthBar"></div>
      <div id="indeedPublisherArea" class="uxHidden">
        <div class="indeedOfficialLabel">Indeed公式ライブ検索（アプリ内）</div>
        <div id="indeedPublisherRoot"></div>
        <div id="indeedPluginStatus" class="indeedPluginStatus"></div>
      </div>
      <div id="indeedDirectArea" class="indeedDirectArea">
        <div class="indeedSearchRow">
          <input id="indeedLiveWhat" type="search" autocomplete="off" aria-label="Indeed検索キーワード" />
          <button id="indeedLiveSearch" type="button">Indeed本体で検索 →</button>
        </div>
        <div id="indeedPresetBar" class="indeedPresetBar"></div>
        <p class="indeedDirectNote">検索結果はIndeed本体で開きます。「在宅」は検索語として扱い、勤務地欄で過度に絞り込みません。</p>
      </div>
      <div id="indeedSeedArea" class="indeedSeedArea"></div>
    `;
    tabs.insertAdjacentElement('afterend',section);

    const input=section.querySelector('#indeedLiveWhat');
    if(input)input.value=String(config.searchWhat||DEFAULT_QUERY).trim()||DEFAULT_QUERY;
    section.querySelector('#indeedLiveSearch')?.addEventListener('click',()=>openIndeed(input?.value));
    input?.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();openIndeed(input.value);}});

    const presetBar=section.querySelector('#indeedPresetBar');
    for(const [label,query] of PRESETS){
      const button=document.createElement('button');
      button.type='button';
      button.className='indeedPreset';
      button.textContent=label;
      button.addEventListener('click',()=>{
        if(input)input.value=query;
        openIndeed(query);
      });
      presetBar?.appendChild(button);
    }
    return section;
  }

  function renderTruthBar(section){
    const bar=section?.querySelector('#indeedTruthBar');
    if(!bar)return;
    const meta=state.meta||{};
    const covered=Number(meta.candidate_indeed_index_profile_coverage_count||0);
    const total=Number(meta.candidate_indeed_index_profile_count||0);
    const seeds=Number(meta.candidate_indeed_index_seed_count||0);
    const finalCount=Number(meta.candidate_final_indeed_apply_jobs||0);
    bar.innerHTML=`
      <span><b>Indeed本文</b> ${configured()?'公式Pluginでライブ表示':'バックエンド未自動取得'}</span>
      <span><b>実URL</b> ${seeds}件</span>
      <span><b>AI適性まで照合</b> ${finalCount}件</span>
      <span><b>探索語カバレッジ</b> ${covered}/${total||'—'}</span>
    `;
  }

  function renderSeeds(section){
    const area=section?.querySelector('#indeedSeedArea');
    if(!area)return;
    area.replaceChildren();
    const raw=Array.isArray(state.meta?.candidate_indeed_index_seeds)?state.meta.candidate_indeed_index_seeds:[];
    const seeds=raw.filter(seed=>seed&&safeIndeedViewjob(seed.url)).slice(0,16);

    const head=document.createElement('div');
    head.className='indeedSeedHead';
    const title=document.createElement('b');
    title.textContent=`Indeed実URL確認 ${seeds.length}件`;
    const note=document.createElement('span');
    note.textContent='公開検索インデックスでIndeed個別URLを確認した候補です。Indeed本文そのものは、このバックエンドでは自動取得していません。';
    head.append(title,note);
    area.appendChild(head);

    if(!seeds.length){
      const empty=document.createElement('div');
      empty.className='indeedSeedEmpty';
      empty.textContent='現在保存されているIndeed実URLはありません。上のIndeed本体検索はいつでも利用できます。';
      area.appendChild(empty);
      return;
    }

    const list=document.createElement('div');
    list.className='indeedSeedList';
    for(const seed of seeds){
      const url=safeIndeedViewjob(seed.url);
      if(!url)continue;
      const card=document.createElement('a');
      card.className='indeedSeedCard';
      card.href=url.toString();
      card.target='_blank';
      card.rel='noopener';
      const main=document.createElement('span');
      main.className='indeedSeedTitle';
      main.textContent=String(seed.title||'Indeed求人');
      const truth=document.createElement('span');
      truth.className='indeedSeedTruth';
      truth.textContent='URL確認済み・本文未自動取得';
      const meta=document.createElement('span');
      meta.className='indeedSeedMeta';
      const profile=String(seed.profile||'').trim();
      meta.textContent=`${ageLabel(seed.last_seen)}${profile?` · ${profile}`:''} · Indeedで本文を見る →`;
      card.append(main,truth,meta);
      list.appendChild(card);
    }
    area.appendChild(list);
  }

  function buildRoot(section){
    const root=section?.querySelector('#indeedPublisherRoot');
    if(!root||root.dataset.ready==='1')return root;
    root.dataset.indeedPluginType='job-search';
    root.dataset.indeedPartnerAppId=String(config.partnerAppId||'').trim();
    root.dataset.indeedPlacementId=String(config.placementId||'').trim();
    root.dataset.indeedSearchLimit=String(Math.max(1,Math.min(20,Number(config.searchLimit)||20)));
    if(String(config.searchWhat||'').trim())root.dataset.indeedSearchWhat=String(config.searchWhat).trim();
    if(String(config.searchWhere||'').trim())root.dataset.indeedSearchWhere=String(config.searchWhere).trim();
    root.dataset.ready='1';
    root.addEventListener('indeed-plugin-event',event=>{
      const detail=event?.detail||{};
      if(detail.type!=='load')return;
      const status=section.querySelector('#indeedPluginStatus');
      if(!status)return;
      status.textContent=detail.payload?.success===true
        ?'Indeed公式Pluginが表示した現在の求人です。'
        :'Indeed公式検索を読み込めませんでした。上のIndeed本体検索は引き続き利用できます。';
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

  function syncSearchFromMain(section){
    const mainSearch=document.querySelector('#search');
    const input=section?.querySelector('#indeedLiveWhat');
    if(!mainSearch||!input)return;
    const typed=String(mainSearch.value||'').trim();
    if(typed)input.value=typed;
  }

  function sync(){
    const section=ensureSection();
    if(!section)return;
    const indeedMode=window.__jobSourceTabs?.mode!=='other';
    section.classList.toggle('uxHidden',!indeedMode);
    if(!indeedMode)return;

    syncSearchFromMain(section);
    renderTruthBar(section);
    renderSeeds(section);

    const publisher=section.querySelector('#indeedPublisherArea');
    publisher?.classList.toggle('uxHidden',!configured());
    if(configured()){
      buildRoot(section);
      loadPlugin();
    }
  }

  const style=document.createElement('style');
  style.textContent=`
    .indeedOfficialSearch{margin:12px 0 16px;border:1px solid #24465f;border-radius:18px;background:#071522;padding:16px;overflow:hidden}
    .indeedOfficialHead{display:flex;flex-direction:column;gap:4px;margin-bottom:10px}.indeedOfficialHead b{font-size:16px;color:#e8f8ff}.indeedOfficialHead span,.indeedPluginStatus,.indeedDirectNote{font-size:10px;color:#91a9bb;line-height:1.65}
    .indeedTruthBar{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin:0 0 12px}.indeedTruthBar span{border:1px solid #17364c;border-radius:10px;background:#081927;padding:8px 9px;font-size:9px;color:#91a9bb;line-height:1.4}.indeedTruthBar b{display:block;color:#dff8ff;font-size:9px;margin-bottom:2px}
    .indeedOfficialLabel{font-size:11px;font-weight:850;color:#7de7f3;margin-bottom:8px}.indeedDirectArea{display:flex;flex-direction:column;gap:8px}.indeedSearchRow{display:grid;grid-template-columns:1fr auto;gap:8px}.indeedSearchRow input{min-width:0;border:1px solid #29475c;border-radius:12px;background:#04111c;color:#e8f8ff;padding:12px 13px;font-size:13px}.indeedSearchRow button{border:0;border-radius:12px;padding:0 16px;background:linear-gradient(135deg,#67e8f9,#a78bfa);color:#06101d;font-size:12px;font-weight:900;cursor:pointer}.indeedPresetBar{display:flex;gap:6px;flex-wrap:wrap}.indeedPreset{border:1px solid #29475c;border-radius:999px;background:#0a1b28;color:#b9ccda;padding:7px 10px;font-size:10px;font-weight:800;cursor:pointer}.indeedPreset:hover{border-color:#67e8f9;color:#eafcff}
    .indeedSeedArea{margin-top:14px;padding-top:13px;border-top:1px solid #173248}.indeedSeedHead{display:flex;flex-direction:column;gap:2px;margin-bottom:8px}.indeedSeedHead b{font-size:12px;color:#e6f8ff}.indeedSeedHead span,.indeedSeedEmpty{font-size:9px;color:#8099ac;line-height:1.55}.indeedSeedList{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.indeedSeedCard{display:flex;flex-direction:column;gap:3px;padding:10px 11px;border:1px solid #1f4058;border-radius:12px;background:#0a1a27;text-decoration:none}.indeedSeedCard:hover{border-color:#67e8f9}.indeedSeedTitle{font-size:11px;font-weight:850;color:#e9f8ff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.indeedSeedTruth{font-size:9px;color:#f4ca7a}.indeedSeedMeta{font-size:9px;color:#79cbd8}.indeedPluginStatus{margin-top:8px}
    @media(max-width:760px){.indeedTruthBar{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media(max-width:650px){.indeedSearchRow{grid-template-columns:1fr}.indeedSearchRow button{padding:12px}.indeedSeedList{grid-template-columns:1fr}}
  `;
  document.head.appendChild(style);

  const previousRender=render;
  render=function(){previousRender();sync();};
  sync();

  window.__indeedOfficial={configured,sync,buildIndeedSearchUrl,normalizeIndeedQuery};
})();
