(()=>{
  'use strict';

  const INTEGRITY_GATE_VERSION=1;
  const CACHE_MIGRATION='candidateIntegrityCacheMigrationV1';
  const SERVER_TRUTH_PIPELINE_VERSION=2;
  const SERVER_TRUTH_CACHE_MIGRATION='candidateServerTruthCacheMigrationV2';

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
    const serverTruthActive=Number(state.meta?.candidate_refresh_pipeline_version||0)>=SERVER_TRUTH_PIPELINE_VERSION;
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

    // The old local reserve was useful while the feed was sparse, but it makes
    // the source tabs lie after a newer server feed removes/reclassifies rows.
    // From pipeline v2 onward, counts and cards must reflect the current server
    // feed only. Saved/applied/declined IDs remain in their separate local keys.
    if(serverTruthActive){
      try{
        if(localStorage.getItem(SERVER_TRUTH_CACHE_MIGRATION)!=='1'){
          localStorage.removeItem(LOCAL_CACHE_KEY);
          localStorage.setItem(SERVER_TRUTH_CACHE_MIGRATION,'1');
        }
      }catch{}
    }

    const merged=coreMergeCandidateStock(serverRows,policyActive,aiPolicyActive);
    if(!serverTruthActive)return merged;
    return merged.filter(row=>row&&row._localReserve!==true);
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
    if(Number(data?.candidate_refresh_pipeline_version||0)>=SERVER_TRUTH_PIPELINE_VERSION){
      node.textContent+=' / 表示件数は最新サーバーfeed基準';
    }
  };

  window.__candidateIntegrity={version:INTEGRITY_GATE_VERSION,serverTruthPipelineVersion:SERVER_TRUTH_PIPELINE_VERSION};
})();
