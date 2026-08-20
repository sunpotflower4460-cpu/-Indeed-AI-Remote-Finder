(()=>{
  'use strict';

  const SOURCE_MODE_KEY='jobSourceModeV1';
  let sourceMode='indeed';
  try{
    const saved=localStorage.getItem(SOURCE_MODE_KEY);
    if(saved==='other'||saved==='indeed')sourceMode=saved;
  }catch{}

  function safeUrl(value){
    try{
      const url=new URL(String(value||''));
      return url.protocol==='https:'?url:null;
    }catch{return null;}
  }

  function isVerifiedIndeed(job){
    if(!job||typeof job!=='object')return false;
    if(String(job.apply_source_kind||'').toLowerCase()!=='indeed')return false;
    const url=safeUrl(job.url);
    if(!url)return false;
    const host=url.hostname.toLowerCase();
    return (host==='indeed.com'||host.endsWith('.indeed.com'))
      &&url.pathname.toLowerCase().includes('/viewjob')
      &&Boolean(url.searchParams.get('jk'));
  }

  function sourceLabel(job){
    if(isVerifiedIndeed(job))return'Indeed';
    const explicit=String(job?.apply_source||'').trim();
    if(explicit)return explicit;
    const via=String(job?.via||'').trim();
    if(via&&!/google jobs/i.test(via))return via;
    const url=safeUrl(job?.url);
    const host=(url?.hostname||'').toLowerCase();
    const known=[
      ['oneforma.com','OneForma'],['outlier.ai','Outlier'],['alignerr.com','Alignerr'],
      ['dataannotation.tech','DataAnnotation'],['telusdigital.com','TELUS Digital'],
      ['ashbyhq.com','Ashby'],['greenhouse.io','Greenhouse'],['lever.co','Lever'],
      ['myworkdayjobs.com','Workday'],['smartrecruiters.com','SmartRecruiters'],
      ['workable.com','Workable'],['rikunabi.com','リクナビNEXT'],['townwork.net','タウンワーク'],
      ['froma.com','フロム・エー ナビ'],['hatalike.jp','はたらいく'],['toranet.jp','とらばーゆ'],
    ];
    for(const [suffix,label] of known){if(host===suffix||host.endsWith('.'+suffix))return label;}
    return'その他の求人サイト';
  }

  function sourceCounts(){
    let indeed=0,other=0;
    for(const job of state.jobs||[]){
      if(!job||!isAvailable(job))continue;
      if(isVerifiedIndeed(job))indeed+=1;else other+=1;
    }
    return{indeed,other};
  }

  const previousCurrentRows=currentRows;
  currentRows=function(){
    const rows=previousCurrentRows();
    return rows.filter(job=>sourceMode==='indeed'?isVerifiedIndeed(job):!isVerifiedIndeed(job));
  };

  function installSourceTabs(){
    const categoryBar=document.querySelector('#uxCategoryBar');
    if(!categoryBar)return;
    let bar=document.querySelector('#uxSourceTabs');
    if(!bar){
      bar=document.createElement('div');
      bar.id='uxSourceTabs';
      bar.className='uxSourceTabs';
      bar.innerHTML='<button class="uxSourceTab" data-source="indeed"></button><button class="uxSourceTab" data-source="other"></button>';
      categoryBar.insertAdjacentElement('beforebegin',bar);
      bar.addEventListener('click',event=>{
        const button=event.target.closest?.('.uxSourceTab');
        if(!button)return;
        sourceMode=button.dataset.source==='other'?'other':'indeed';
        try{localStorage.setItem(SOURCE_MODE_KEY,sourceMode)}catch{}
        render();
      });
    }
    const counts=sourceCounts();
    const indeed=bar.querySelector('[data-source="indeed"]');
    const other=bar.querySelector('[data-source="other"]');
    if(indeed)indeed.textContent=`Indeed ${counts.indeed}件`;
    if(other)other.textContent=`その他の求人サイト ${counts.other}件`;
    bar.querySelectorAll('.uxSourceTab').forEach(button=>button.classList.toggle('active',button.dataset.source===sourceMode));
  }

  function decorateContainer(container,job,{compact=false}={}){
    if(!container||!job)return;
    const label=sourceLabel(job);
    if(compact){
      const meta=container.querySelector('.uxAltMain span');
      if(meta&&!meta.dataset.sourceDecorated){
        meta.textContent=`掲載元：${label} · ${meta.textContent}`;
        meta.dataset.sourceDecorated='1';
      }
    }else{
      const top=container.querySelector('.uxTopline');
      if(top&&!top.querySelector('.uxSourceBadge')){
        const badge=document.createElement('span');
        badge.className='uxSourceBadge';
        badge.textContent=`掲載元：${label}`;
        top.insertAdjacentElement('afterend',badge);
      }
    }

    if(sourceMode==='other'){
      const primary=container.querySelector('.uxIndeed');
      const direct=safeUrl(job.url);
      if(primary&&direct){
        primary.href=direct.toString();
        primary.textContent=`${label}で求人を見る →`;
        primary.classList.remove('uxIndeed');
        primary.classList.add('uxSourcePrimary');
      }
      container.querySelector('.uxOfficial')?.classList.add('uxHidden');
      container.querySelector('.uxIndeedNote')?.remove();
      const altLinks=container.querySelector('.uxAltLinks');
      if(altLinks&&direct){
        const links=altLinks.querySelectorAll('a');
        if(links[0]){links[0].href=direct.toString();links[0].textContent=label;}
        if(links[1])links[1].classList.add('uxHidden');
      }
    }
  }

  function decorateCards(){
    const byId=new Map((state.jobs||[]).filter(Boolean).map(job=>[String(job.id),job]));
    document.querySelectorAll('#jobs .uxCard').forEach(card=>{
      const id=String(card.querySelector('[data-id]')?.dataset.id||'');
      decorateContainer(card,byId.get(id));
      card.querySelectorAll('.uxAlt').forEach(alt=>{
        const altId=String(alt.querySelector('[data-id]')?.dataset.id||'');
        decorateContainer(alt,byId.get(altId),{compact:true});
      });
    });
  }

  function clarifyEmptyState(){
    const empty=document.querySelector('#jobs .empty');
    if(!empty)return;
    if(sourceMode==='indeed'){
      empty.innerHTML='<b>現在、Indeed掲載を確認できた候補はありません。</b><br>他サイトの求人とは分けて表示しています。次回の自動更新ではIndeed候補を優先して探します。';
    }else{
      empty.innerHTML='<b>現在、その他の求人サイトの候補はありません。</b><br>上の「Indeed」に切り替えるとIndeed確認済み求人を表示します。';
    }
  }

  function updateSourceCopy(){
    const hero=document.querySelector('.hero p');
    if(hero)hero.textContent='まずIndeedに掲載されている候補を表示します。Indeed以外の求人は「その他の求人サイト」に分離し、掲載元を明記しています。英語原文や細かな判定は「詳しく見る」に収納しています。';
    const openIndeed=document.querySelector('#openIndeed');
    if(openIndeed)openIndeed.textContent='Indeedを直接開く';
  }

  function installStyles(){
    const style=document.createElement('style');
    style.textContent=`
      .uxSourceTabs{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:10px}.uxSourceTab{appearance:none;border:1px solid var(--line);background:#071522;color:#a8bfd2;border-radius:12px;padding:11px 8px;font-size:11px;font-weight:850;cursor:pointer}.uxSourceTab.active{background:#e7f8ff;color:#06101d;border-color:#e7f8ff}.uxSourceBadge{display:inline-block;margin:-2px 0 7px;font-size:9px;font-weight:850;color:#88dff0;background:#102b3c;border-radius:999px;padding:4px 7px}.uxSourcePrimary{font-size:13px!important;padding:13px 12px!important;background:linear-gradient(135deg,#67e8f9,#a78bfa)!important;color:#06101d!important}.uxAltLinks a.uxHidden{display:none!important}
      @media(max-width:500px){.uxSourceTabs{grid-template-columns:1fr}.uxSourceTab{padding:10px}}
    `;
    document.head.appendChild(style);
  }

  installStyles();
  updateSourceCopy();

  const previousRender=render;
  render=function(){
    previousRender();
    installSourceTabs();
    decorateCards();
    clarifyEmptyState();
  };

  if(Array.isArray(state.jobs)&&state.jobs.length)render();

  window.__jobSourceTabs={isVerifiedIndeed,sourceLabel,get mode(){return sourceMode;}};
})();
