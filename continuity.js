(()=>{
  'use strict';

  // A listing can move from Indeed to an employer/provider URL while remaining
  // the same company/title opportunity. Keep user actions attached to that
  // stable identity so a source-ID change never makes an applied/declined job
  // look new again.
  const APPLIED_FP_KEY='appliedJobFingerprintsV1';
  const DECLINED_FP_KEY='declinedJobFingerprintsV1';
  const APPLIED_FP_AT_KEY='appliedFingerprintAtV1';
  const appliedFingerprints=loadSet(APPLIED_FP_KEY);
  const declinedFingerprints=loadSet(DECLINED_FP_KEY);
  const appliedFingerprintAt=loadMap(APPLIED_FP_AT_KEY);

  function normalizedIdentity(value=''){
    return String(value||'')
      .normalize('NFKC')
      .toLowerCase()
      .replace(/[\s\-_–—|｜・/\\()[\]{}【】『』「」]+/g,'')
      .trim();
  }

  function candidateFingerprint(job){
    const company=normalizedIdentity(job?.company);
    const title=normalizedIdentity(job?.title);
    if(company&&title)return`${company}|${title}`;
    return job?.id?`id:${String(job.id)}`:'';
  }

  function knownRows(){
    const byId=new Map();
    for(const row of [...loadCachedJobs(),...state.jobs]){
      if(row?.id)byId.set(String(row.id),row);
    }
    return byId;
  }

  function persistFingerprints(){
    persistSet(APPLIED_FP_KEY,appliedFingerprints);
    persistSet(DECLINED_FP_KEY,declinedFingerprints);
    persistMap(APPLIED_FP_AT_KEY,appliedFingerprintAt);
  }

  function migrateLegacyActionIds(){
    const rows=knownRows();
    for(const id of state.applied){
      const row=rows.get(String(id));
      const fp=candidateFingerprint(row);
      if(!fp)continue;
      appliedFingerprints.add(fp);
      declinedFingerprints.delete(fp);
      if(!appliedFingerprintAt[fp]&&state.appliedAt[id]){
        appliedFingerprintAt[fp]=state.appliedAt[id];
      }
    }
    for(const id of state.declined){
      const row=rows.get(String(id));
      const fp=candidateFingerprint(row);
      if(!fp)continue;
      declinedFingerprints.add(fp);
      appliedFingerprints.delete(fp);
      delete appliedFingerprintAt[fp];
    }
  }

  function reconcileCurrentActionIds(){
    migrateLegacyActionIds();
    for(const row of state.jobs){
      if(!row?.id)continue;
      const id=String(row.id);
      const fp=candidateFingerprint(row);
      if(!fp)continue;
      if(declinedFingerprints.has(fp)){
        state.declined.add(id);
        state.applied.delete(id);
        delete state.appliedAt[id];
      }else if(appliedFingerprints.has(fp)){
        state.applied.add(id);
        state.declined.delete(id);
        if(appliedFingerprintAt[fp]&&!state.appliedAt[id]){
          state.appliedAt[id]=appliedFingerprintAt[fp];
        }
      }
    }
    persistSet('declinedJobs',state.declined);
    persistSet('appliedJobs',state.applied);
    persistMap('appliedAt',state.appliedAt);
    persistFingerprints();
  }

  // Migrate/apply the stable identity before every render. This means loadFeed()
  // can replace an Indeed row with an official-provider row without resurrecting
  // an opportunity the user already handled.
  const coreRender=render;
  render=function(){
    reconcileCurrentActionIds();
    coreRender();
    relabelDirectOfficialVerification();
  };

  // Capture the user's intended transition before app.js mutates the id-based
  // compatibility sets in its onclick handler.
  document.addEventListener('click',event=>{
    const button=event.target.closest?.('.applied,.decline');
    if(!button)return;
    const id=String(button.dataset.id||'');
    const row=state.jobs.find(item=>String(item?.id||'')===id);
    const fp=candidateFingerprint(row);
    if(!fp)return;

    if(button.classList.contains('applied')){
      const undo=state.applied.has(id)||appliedFingerprints.has(fp);
      if(undo){
        appliedFingerprints.delete(fp);
        delete appliedFingerprintAt[fp];
      }else{
        appliedFingerprints.add(fp);
        declinedFingerprints.delete(fp);
        appliedFingerprintAt[fp]=`${localDateKey()}T${new Date().toTimeString().slice(0,8)}`;
      }
    }else{
      const undo=state.declined.has(id)||declinedFingerprints.has(fp);
      if(undo){
        declinedFingerprints.delete(fp);
      }else{
        declinedFingerprints.add(fp);
        appliedFingerprints.delete(fp);
        delete appliedFingerprintAt[fp];
      }
    }
    persistFingerprints();
  },true);

  // Count unique opportunities, not URL/ID variants of the same job.
  todayAppliedCount=function(){
    migrateLegacyActionIds();
    const today=localDateKey();
    return Object.entries(appliedFingerprintAt)
      .filter(([fp,when])=>appliedFingerprints.has(fp)&&String(when||'').startsWith(today))
      .length;
  };

  // PR #75 taught the PWA to trust a recent employer-ATS live check for
  // freshness. Direct audited provider pages use official_live_verified_at
  // instead, so give them the same freshness semantics without pretending they
  // are an ATS or weakening the three-day live-verification window.
  function isDirectOfficialVerified(job){
    if(!job||typeof job!=='object')return false;
    const source=String(job.discovery_source||'');
    const direct=source==='official-provider-page'
      ||source==='official-provider-page-japan-depth'
      ||Number(job.direct_official_source_version||0)>0
      ||Number(job.official_japan_depth_version||0)>0;
    const liveAge=ageDays(job.official_live_verified_at);
    return direct&&liveAge!==null&&liveAge<=ATS_LIVE_MAX_DAYS;
  }

  const coreIsLiveATSVerified=isLiveATSVerified;
  isLiveATSVerified=function(job){
    return coreIsLiveATSVerified(job)||isDirectOfficialVerified(job);
  };

  const coreFreshnessReference=freshnessReference;
  freshnessReference=function(job){
    if(isDirectOfficialVerified(job))return job.official_live_verified_at;
    return coreFreshnessReference(job);
  };

  function relabelDirectOfficialVerification(){
    const byId=new Map(state.jobs.filter(Boolean).map(job=>[String(job.id),job]));
    document.querySelectorAll('#jobs article.card').forEach(card=>{
      const button=card.querySelector('[data-id]');
      const row=button?byId.get(String(button.dataset.id||'')):null;
      if(!isDirectOfficialVerified(row))return;
      card.querySelectorAll('.tag').forEach(tag=>{
        if(tag.textContent.trim()==='公式ATS掲載確認済み')tag.textContent='公式掲載確認済み';
      });
      const meta=card.querySelector('.meta');
      if(meta){
        meta.textContent=meta.textContent.replace(
          /公式ATS確認:\s*不明/,
          `公式掲載確認: ${fmtDate(row.official_live_verified_at)}`
        );
      }
    });
  }

  window.__candidateContinuity={
    candidateFingerprint,
    appliedFingerprints,
    declinedFingerprints,
    isDirectOfficialVerified,
  };
})();
