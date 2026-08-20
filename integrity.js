(()=>{
  'use strict';

  const INTEGRITY_GATE_VERSION=1;
  const CACHE_MIGRATION='candidateIntegrityCacheMigrationV1';

  // Once the server activates the integrity gate, old device reserve rows must
  // not bypass Japan-compatibility / personal-identity exclusions.
  const coreQualityEligible=qualityEligible;
  qualityEligible=function(job,policyActive=true,aiPolicyActive=true){
    if(!coreQualityEligible(job,policyActive,aiPolicyActive))return false;
    const integrityActive=Number(state.meta?.candidate_integrity_gate_version||0)>=INTEGRITY_GATE_VERSION;
    if(!integrityActive)return true;
    return Number(job?.candidate_integrity_gate_version||0)>=INTEGRITY_GATE_VERSION
      &&job?.human_identity_dependency==='none-detected';
  };

  const coreMergeCandidateStock=mergeCandidateStock;
  mergeCandidateStock=function(serverRows,policyActive,aiPolicyActive){
    const integrityActive=Number(state.meta?.candidate_integrity_gate_version||0)>=INTEGRITY_GATE_VERSION;
    if(integrityActive){
      try{
        if(localStorage.getItem(CACHE_MIGRATION)!=='1'){
          localStorage.removeItem(LOCAL_CACHE_KEY);
          localStorage.setItem(CACHE_MIGRATION,'1');
        }
      }catch{}
      serverRows=(serverRows||[]).filter(row=>
        Number(row?.candidate_integrity_gate_version||0)>=INTEGRITY_GATE_VERSION
        &&row?.human_identity_dependency==='none-detected'
      );
    }
    return coreMergeCandidateStock(serverRows,policyActive,aiPolicyActive);
  };

  const coreUpdateHealth=updateHealth;
  updateHealth=function(data){
    coreUpdateHealth(data);
    if(Number(data?.candidate_integrity_gate_version||0)<INTEGRITY_GATE_VERSION)return;
    const node=document.querySelector('#sourceHealth');
    if(!node)return;
    const dropped=Number(data.candidate_integrity_dropped||0);
    const semantic=Number(data.candidate_semantic_duplicates_dropped||0);
    node.textContent+=` / 日本適合・本人依存ゲート有効${dropped?`・不適合 ${dropped}件除外`:''}${semantic?`・類似 ${semantic}件統合`:''}`;
  };

  window.__candidateIntegrity={version:INTEGRITY_GATE_VERSION};
})();
