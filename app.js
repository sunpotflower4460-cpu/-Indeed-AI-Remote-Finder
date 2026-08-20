const $=s=>document.querySelector(s);
const DEFAULT_VISIBLE=30;
const DAILY_TARGET=10;
const USER_STOCK_TARGET=100;
const LOCAL_POOL_LIMIT=150;
const LOCAL_CACHE_KEY='candidateCacheV5';
const LOCAL_RESERVE_MAX_DAYS=14;
const QUALITY_POLICY_VERSION=2;
const QUALITY_GATE='async-ai-remote-v2';
const PRESENCE_GATE_VERSION=1;
const AI_TOOL_POLICY_GATE_VERSION=1;
const REVIEW_AUTOMATION_MIN=64;
const REVIEW_HUMAN_RISK_MAX=18;
const REVIEW_AUTOMATION_SIGNAL_MIN=2;
const LLM_PRESENCE_TERMS=['本人待機','人間の待機','在席','カメラ','webcam','画面共有','本人確認','離席不可','human standby','human presence','at the desk','at the computer','attendance check','presence monitoring'];

function loadSet(key){
  try{const v=JSON.parse(localStorage.getItem(key)||'[]');return new Set(Array.isArray(v)?v.map(String):[])}catch{return new Set()}
}
function loadMap(key){
  try{const v=JSON.parse(localStorage.getItem(key)||'{}');return v&&typeof v==='object'&&!Array.isArray(v)?v:{}}catch{return{}}
}
function persistSet(key,value){try{localStorage.setItem(key,JSON.stringify([...value]))}catch{}}
function persistMap(key,value){try{localStorage.setItem(key,JSON.stringify(value))}catch{}}
function loadCachedJobs(){
  try{const v=JSON.parse(localStorage.getItem(LOCAL_CACHE_KEY)||'[]');return Array.isArray(v)?v.filter(x=>x&&typeof x==='object'):[]}catch{return[]}
}
function persistCachedJobs(rows){
  try{
    const clean=rows.slice(0,LOCAL_POOL_LIMIT).map(row=>{const copy={...row};delete copy._localReserve;return copy;});
    localStorage.setItem(LOCAL_CACHE_KEY,JSON.stringify(clean));
  }catch{}
}

const legacyHidden=loadSet('hiddenJobs');
const declined=loadSet('declinedJobs');
legacyHidden.forEach(id=>declined.add(id));
persistSet('declinedJobs',declined);

const state={
  jobs:[],mode:'all',q:'',sort:'best',displayLimit:DEFAULT_VISIBLE,
  favorite:loadSet('savedJobs'),declined,
  applied:loadSet('appliedJobs'),appliedAt:loadMap('appliedAt'),meta:{}
};

function esc(s=''){return String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function parseDate(s){if(!s)return null;const d=new Date(s);return Number.isNaN(+d)?null:d;}
function fmtDate(s){const d=parseDate(s);if(!d)return'不明';return new Intl.DateTimeFormat('ja-JP',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(d)}
function ageDays(s){const d=parseDate(s);if(!d)return null;return Math.max(0,(Date.now()-d.getTime())/864e5);}
function ageLabel(s){const d=parseDate(s);if(!d)return'日付不明';const h=Math.max(0,(Date.now()-d.getTime())/36e5);if(h<24)return`${Math.max(1,Math.round(h))}時間以内`;return`${Math.floor(h/24)}日前目安`;}
function meterClass(v){return v>=82?'good':v>=64?'warn':'bad'}
function effectiveTier(j){const age=ageDays(j.search_published_at);if(age!==null&&age>30)return'expired';if(j.tier==='high'&&(age===null||age>14))return'review';return j.tier||'review';}
function feedAgeHours(){const d=parseDate(state.meta.generated_at);return d?Math.max(0,(Date.now()-d.getTime())/36e5):null;}
function reviewStrictContextValid(j){
  if(j?.tier!=='review')return false;
  const reasons=new Set((j.automation_reasons||[]).map(x=>String(x||'').trim().toLowerCase()).filter(Boolean));
  return Number(j.quality_policy_version||0)===QUALITY_POLICY_VERSION
    &&j.quality_gate===QUALITY_GATE
    &&j.autonomy_attention_risk==='low'
    &&j.remote_search_only!==true
    &&Number(j.automation_confidence||0)>=REVIEW_AUTOMATION_MIN
    &&Number(j.human_dependency_risk||0)<=REVIEW_HUMAN_RISK_MAX
    &&reasons.size>=REVIEW_AUTOMATION_SIGNAL_MIN
    &&j.full_listing_presence_screened===true
    &&Number(j.presence_gate_version||0)===PRESENCE_GATE_VERSION
    &&j.continuous_presence_risk==='low';
}
function hasDualPass(j){
  if(j?.llm_strict_pass!==true||j?.llm_review?.strict_pass!==true||effectiveTier(j)==='expired')return false;
  if(j.tier==='high')return true;
  return reviewStrictContextValid(j);
}
function recommendationMode(){return['all','high','review','dual'].includes(state.mode)}
function resetWindow(){state.displayLimit=DEFAULT_VISIBLE;}
function localDateKey(d=new Date()){return`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
function todayAppliedCount(){const today=localDateKey();return[...state.applied].filter(id=>String(state.appliedAt[id]||'').startsWith(today)).length;}
function isNewCandidate(j){return(ageDays(j.first_seen)??99)<1.5&&!j.carryover&&!j._localReserve;}
function isCurrentEnough(j){const seen=ageDays(j.last_seen);const published=ageDays(j.search_published_at);return(seen===null||seen<=LOCAL_RESERVE_MAX_DAYS)&&(published===null||published<=30);}
function llmQualityRejected(j){
  const r=j?.llm_review;if(!r||typeof r!=='object')return false;
  const confidence=Number(r.confidence||0),automatable=Number(r.automatable_fraction||0),blockers=Array.isArray(r.blockers)?r.blockers.filter(Boolean):[];
  if(r.verdict==='reject'||r.physical_presence_required===true||r.synchronous_human_interaction==='frequent'||r.human_dependency==='high')return true;
  if(confidence>=80&&(r.synchronous_human_interaction==='occasional'||r.human_dependency==='medium'||automatable<75))return true;
  const blockerText=blockers.join(' ').toLowerCase();
  if(confidence>=75&&LLM_PRESENCE_TERMS.some(term=>blockerText.includes(term.toLowerCase())))return true;
  return confidence>=85&&blockers.length>0&&automatable<90;
}
function aiPolicyEligible(j,aiPolicyActive=true){
  if(!aiPolicyActive)return true;
  if(Number(j.ai_tool_policy_gate_version||0)!==AI_TOOL_POLICY_GATE_VERSION)return false;
  if(j.ai_tool_policy_status==='prohibited')return false;
  return j.ai_tool_policy_status==='explicitly-allowed'||j.ai_tool_policy_status==='not-stated';
}
function qualityEligible(j,policyActive=true,aiPolicyActive=true){
  if(!isCurrentEnough(j)||llmQualityRejected(j)||!aiPolicyEligible(j,aiPolicyActive))return false;
  if(!policyActive)return true;
  if(Number(j.quality_policy_version||0)!==QUALITY_POLICY_VERSION||j.quality_gate!==QUALITY_GATE)return false;
  if(j.autonomy_attention_risk!=='low'||j.remote_search_only===true)return false;
  if(j.full_listing_presence_screened!==true||Number(j.presence_gate_version||0)!==PRESENCE_GATE_VERSION||j.continuous_presence_risk!=='low')return false;
  if(effectiveTier(j)==='review'){
    if(Number(j.automation_confidence||0)<REVIEW_AUTOMATION_MIN||Number(j.human_dependency_risk||0)>REVIEW_HUMAN_RISK_MAX)return false;
    const reasons=new Set((j.automation_reasons||[]).map(x=>String(x||'').trim().toLowerCase()).filter(Boolean));
    if(reasons.size<REVIEW_AUTOMATION_SIGNAL_MIN)return false;
  }
  return true;
}
function isAvailable(j){const id=String(j.id);return effectiveTier(j)!=='expired'&&!state.declined.has(id)&&!state.applied.has(id);}

function mergeCandidateStock(serverRows,policyActive,aiPolicyActive){
  const map=new Map();
  for(const row of loadCachedJobs()){
    if(!row?.id||!qualityEligible(row,true,true))continue;
    map.set(String(row.id),{...row,_localReserve:true});
  }
  for(const row of serverRows){
    if(!row?.id||!qualityEligible(row,policyActive,aiPolicyActive))continue;
    map.set(String(row.id),{...row,_localReserve:false});
  }
  const rows=[...map.values()];
  rows.sort((a,b)=>(+parseDate(b.last_seen)||0)-(+parseDate(a.last_seen)||0)||(b.score||0)-(a.score||0));
  persistCachedJobs(rows);
  return rows.slice(0,LOCAL_POOL_LIMIT);
}

function updateStats(){
  const available=state.jobs.filter(isAvailable).length;
  const high=state.jobs.filter(j=>isAvailable(j)&&effectiveTier(j)==='high').length;
  $('#countAvailable').textContent=available;
  $('#countHigh').textContent=high;
  $('#todayApplied').textContent=`${todayAppliedCount()}/${DAILY_TARGET}`;
  $('#updated').textContent=fmtDate(state.meta.generated_at);
}

function currentRows(){
  const q=state.q.trim().toLowerCase();
  let rows=state.jobs.filter(j=>{
    const id=String(j.id),tier=effectiveTier(j),isDeclined=state.declined.has(id),isFavorite=state.favorite.has(id),isApplied=state.applied.has(id);
    if(state.mode==='declined')return isDeclined;
    if(state.mode==='applied')return isApplied&&!isDeclined;
    if(state.mode==='favorite')return isFavorite&&!isDeclined;
    if(isDeclined||isApplied)return false;
    if(state.mode==='dual')return hasDualPass(j);
    if(state.mode==='all')return tier!=='expired';
    return tier===state.mode;
  });
  if(q)rows=rows.filter(j=>`${j.title} ${j.company||''} ${j.location||''} ${j.snippet||''} ${(j.tags||[]).join(' ')} ${(j.automation_reasons||[]).join(' ')} ${j.llm_review?.automation_summary||''} ${(j.llm_review?.automation_plan||[]).join(' ')}`.toLowerCase().includes(q));
  rows=[...rows];
  if(state.sort==='fresh')rows.sort((a,b)=>(+parseDate(b.search_published_at)||0)-(+parseDate(a.search_published_at)||0)||(b.score||0)-(a.score||0));
  else if(state.sort==='auto')rows.sort((a,b)=>(b.automation_confidence||0)-(a.automation_confidence||0)||(b.remote_confidence||0)-(a.remote_confidence||0));
  else if(state.sort==='llm')rows.sort((a,b)=>(b.llm_review?.automatable_fraction??-1)-(a.llm_review?.automatable_fraction??-1)||(b.llm_review?.confidence??-1)-(a.llm_review?.confidence??-1));
  else rows.sort((a,b)=>{
    const rank={high:0,review:1,expired:2,hidden:3};
    return(hasDualPass(b)?1:0)-(hasDualPass(a)?1:0)
      ||(b.llm_review?1:0)-(a.llm_review?1:0)
      ||(rank[effectiveTier(a)]??9)-(rank[effectiveTier(b)]??9)
      ||(isNewCandidate(b)?1:0)-(isNewCandidate(a)?1:0)
      ||(a._localReserve?1:0)-(b._localReserve?1:0)
      ||(a.carryover?1:0)-(b.carryover?1:0)
      ||(b.score||0)-(a.score||0)
      ||(b.freshness_confidence||0)-(a.freshness_confidence||0);
  });
  return rows;
}

function reasonText(j){const r=(j.automation_reasons||[]).slice(0,4);return r.length?`AI化しやすい根拠: ${r.join('・')}`:'仕事内容の詳細確認が必要';}
function verdictText(tier){return tier==='high'?'高確度':tier==='expired'?'期限超過':'次点候補';}
function listItems(items){return(items||[]).map(x=>`<li>${esc(x)}</li>`).join('');}
function llmPanel(j){
  const r=j.llm_review;if(!r)return'';
  const verdict={strong:'強い候補',uncertain:'不確定',reject:'不適合'}[r.verdict]||r.verdict,strict=hasDualPass(j);
  return `<details class="llmBox" ${strict?'open':''}><summary>${strict?'◎ LLM二重審査通過':'LLM二次審査'} · 技術代替 ${esc(r.automatable_fraction)}% · 確信 ${esc(r.confidence)}%</summary><div class="llmGrid"><div><span>判定</span><b>${esc(verdict)}</b></div><div><span>人間依存</span><b>${esc(r.human_dependency)}</b></div><div><span>同期対応</span><b>${esc(r.synchronous_human_interaction)}</b></div><div><span>データ注意</span><b>${esc(r.data_sensitivity_risk)}</b></div></div>${r.automation_summary?`<p>${esc(r.automation_summary)}</p>`:''}${r.automation_plan?.length?`<div class="llmSection"><b>自動化レシピ</b><ol>${listItems(r.automation_plan)}</ol></div>`:''}${r.blockers?.length?`<div class="llmSection risk"><b>技術的ブロッカー</b><ul>${listItems(r.blockers)}</ul></div>`:''}${r.questions_to_confirm?.length?`<div class="llmSection"><b>応募後に確認</b><ul>${listItems(r.questions_to_confirm)}</ul></div>`:''}</details>`;
}

function render(){
  updateStats();
  const rows=currentRows();
  const visible=recommendationMode()?rows.slice(0,state.displayLimit):rows;
  $('#resultCount').textContent=recommendationMode()&&rows.length>visible.length?`${visible.length} / ${rows.length}件`:`${rows.length}件`;
  const names={high:'高確度だけ',dual:'LLM二重審査済み',review:'次点候補',all:'おすすめ候補',favorite:'お気に入り',applied:'応募済み',declined:'応募しない'};
  $('#listTitle').textContent=names[state.mode]||'求人候補';
  if(!rows.length){
    $('#jobs').innerHTML=`<div class="empty"><b>この条件では候補がありません。</b><br>${state.mode==='applied'?'まだ応募済みの求人はありません。':state.mode==='declined'?'「応募しない」にした求人はありません。':'候補プールは毎日補充されます。'}<br><span>${state.mode==='dual'?'二重審査通過がなくても「おすすめ候補」には次点候補を表示します。':'「おすすめ候補」へ戻すか「最新候補を再読込」を試せます。'}</span></div>`;
    return;
  }
  let html=visible.map(j=>{
    const id=String(j.id),favorite=state.favorite.has(id),declined=state.declined.has(id),applied=state.applied.has(id),tier=effectiveTier(j),high=tier==='high',dual=hasDualPass(j),published=j.search_published_at||j.last_seen,org=[j.company,j.location].filter(Boolean).map(esc).join(' · '),isNew=isNewCandidate(j);
    const aiPolicyTag=j.ai_tool_policy_status==='explicitly-allowed'?'<span class="tag autonomyTag">AI利用可明記</span>':j.ai_tool_use_permission_confirm_required===true?'<span class="tag checkTag">AI利用可否確認</span>':'';
    const verifyDays=Number.isFinite(Number(j.verification_age_days))?Math.max(0,Number(j.verification_age_days)):Math.max(0,Math.floor(ageDays(j.last_seen)||0));
    const reserveNote=j.carryover||j._localReserve?`<div class="reserveNote">${verifyDays>0?`最終検出から${esc(verifyDays)}日未再検出。`:'今回の検索では未再検出。'}品質確認済みの予備候補ですが、リンク先で募集継続を確認してください。</div>`:'';
    const policyNote=j.ai_tool_use_permission_confirm_required===true?'<div class="checkNote">求人票ではAI利用許可を確認できていません。応募・業務開始前に生成AI／外部AIの利用可否を確認してください。</div>':'';
    return `<article class="card ${high?'high':''} ${dual?'dualCard':''} ${tier==='expired'?'expired':''}"><div class="cardHead"><div class="verdict ${dual?'dualBadge':high?'ok':tier==='expired'?'expiredBadge':'review'}">${dual?'◎ 二重審査通過':verdictText(tier)}</div><div class="fresh">${esc(ageLabel(published))}</div></div><h3>${esc(j.title)}</h3>${org?`<div class="org">${org}</div>`:''}<p class="snippet">${esc(j.snippet||'求人概要なし')}</p><div class="scores"><div><span>AI代替</span><b class="${meterClass(j.automation_confidence)}">${j.automation_confidence??'-'}</b></div><div><span>完全在宅</span><b class="${meterClass(j.remote_confidence)}">${j.remote_confidence??'-'}</b></div><div><span>新しさ</span><b class="${meterClass(j.freshness_confidence)}">${j.freshness_confidence??'-'}</b></div></div><div class="why">${esc(reasonText(j))}</div><div class="tags">${isNew?'<span class="tag repeat">NEW</span>':''}${j.autonomy_attention_risk==='low'?'<span class="tag autonomyTag">張り付きリスク低</span>':''}${aiPolicyTag}${(j.tags||[]).filter(t=>t!=='張り付きリスク低').slice(0,5).map(t=>`<span class="tag">${esc(t)}</span>`).join('')}${j.llm_review?'<span class="tag dualTag">LLM監査済み</span>':''}${j.seen_count>1?`<span class="tag repeat">再検出 ${j.seen_count}回</span>`:''}${j.duplicate_count>1?`<span class="tag">類似掲載 ${j.duplicate_count}件を統合</span>`:''}${j.carryover?'<span class="tag carry">予備・今回未再検出</span>':''}${j._localReserve?'<span class="tag carry">端末予備</span>':''}${dual?'<span class="tag dualTag">LLM二重審査 ✓</span>':''}${favorite?'<span class="tag favoriteTag">お気に入り</span>':''}${applied?'<span class="tag appliedTag">応募済み</span>':''}${declined?'<span class="tag declinedTag">応募しない</span>':''}</div>${reserveNote}${policyNote}${j.risk_reasons?.length?`<div class="risk">要注意: ${esc(j.risk_reasons.join('・'))}</div>`:''}${llmPanel(j)}${tier==='expired'?'<div class="risk">掲載日から30日を超えたため通常一覧から除外しています。</div>':''}<div class="actions"><button class="btn ghost favorite" data-id="${esc(id)}">${favorite?'★ お気に入り':'☆ お気に入り'}</button><button class="btn ghost applied" data-id="${esc(id)}">${applied?'↩ 応募済み解除':'✓ 応募済みにする'}</button><button class="btn ghost decline" data-id="${esc(id)}">${declined?'↩ 候補に戻す':'× 応募しない'}</button><a class="btn primary" href="${esc(j.url)}" target="_blank" rel="noopener noreferrer">求人を確認・応募 →</a></div><div class="meta">掲載目安: ${esc(j.posted_label||fmtDate(j.search_published_at))} / 最終検出: ${esc(fmtDate(j.last_seen))}${j.llm_model?` / LLM: ${esc(j.llm_model)}`:''}</div></article>`;
  }).join('');
  if(recommendationMode()&&visible.length<rows.length)html+=`<button id="loadMore" class="btn ghost moreBtn">次の候補を${Math.min(DEFAULT_VISIBLE,rows.length-visible.length)}件見る</button>`;
  $('#jobs').innerHTML=html;
  document.querySelectorAll('.favorite').forEach(b=>b.onclick=()=>{const id=b.dataset.id;if(state.favorite.has(id))state.favorite.delete(id);else state.favorite.add(id);persistSet('savedJobs',state.favorite);render();});
  document.querySelectorAll('.decline').forEach(b=>b.onclick=()=>{const id=b.dataset.id;if(state.declined.has(id)){state.declined.delete(id)}else{state.declined.add(id);state.favorite.delete(id);state.applied.delete(id);delete state.appliedAt[id]}persistSet('declinedJobs',state.declined);persistSet('savedJobs',state.favorite);persistSet('appliedJobs',state.applied);persistMap('appliedAt',state.appliedAt);render();});
  document.querySelectorAll('.applied').forEach(b=>b.onclick=()=>{const id=b.dataset.id;if(state.applied.has(id)){state.applied.delete(id);delete state.appliedAt[id]}else{state.applied.add(id);state.declined.delete(id);state.appliedAt[id]=`${localDateKey()}T${new Date().toTimeString().slice(0,8)}`}persistSet('appliedJobs',state.applied);persistSet('declinedJobs',state.declined);persistMap('appliedAt',state.appliedAt);render();});
  const more=$('#loadMore');if(more)more.onclick=()=>{state.displayLimit+=DEFAULT_VISIBLE;render();};
}

function updateHealth(d){
  const h=feedAgeHours();
  let text=d.provider_configured===false?'求人自動更新はSERPAPI_KEY設定後に有効':d.query_total?`自動検索 ${d.query_success||0}/${d.query_total}・Indeed応募URL ${d.indeed_apply_jobs??'-'}件`:'自動検索 -';
  const serverPool=Number.isInteger(d.candidate_pool_size)?d.candidate_pool_size:0;
  const available=state.jobs.filter(isAvailable).length;
  text+=` / サーバー候補 ${serverPool}件・手元未応募 ${available}件`;
  if(Number.isInteger(d.new_jobs))text+=`・新着 ${d.new_jobs}件`;
  if(Number.isInteger(d.live_jobs))text+=`・今回検出 ${d.live_jobs}件`;
  if(Number.isInteger(d.carryover_jobs)&&d.carryover_jobs>0)text+=`・予備 ${d.carryover_jobs}件`;
  if(Number.isInteger(d.presence_quality_dropped)&&d.presence_quality_dropped>0)text+=`・本人在席要件 ${d.presence_quality_dropped}件除外`;
  if(Number.isInteger(d.llm_quality_dropped)&&d.llm_quality_dropped>0)text+=`・LLM品質除外 ${d.llm_quality_dropped}件`;
  if(Number.isInteger(d.candidate_ai_tool_policy_dropped)&&d.candidate_ai_tool_policy_dropped>0)text+=`・AI利用禁止 ${d.candidate_ai_tool_policy_dropped}件除外`;
  if(Number.isInteger(d.candidate_ai_tool_policy_confirmation_required)&&d.candidate_ai_tool_policy_confirmation_required>0)text+=`・AI利用可否要確認 ${d.candidate_ai_tool_policy_confirmation_required}件`;
  if(Number.isInteger(d.serpapi_paginated_requests_run)&&d.serpapi_paginated_requests_run>0)text+=`・追加ページ ${d.serpapi_paginated_requests_run}回`;
  if(Number.isInteger(d.serpapi_requests_month)&&Number.isInteger(d.serpapi_monthly_request_cap))text+=` / 検索API ${d.serpapi_requests_month}/${d.serpapi_monthly_request_cap}`;
  if(d.remote_contradiction_dropped>0)text+=` / リモート矛盾 ${d.remote_contradiction_dropped}件除外`;
  if(d.llm_provider_configured===false)text+=' / LLM二次審査はOPENAI_API_KEY未設定';
  else if(d.llm_provider_configured===true){text+=` / LLM審査 ${d.llm_reviewed_jobs||0}件・二重通過 ${d.llm_strict_jobs||0}件`;if(Number.isInteger(d.llm_paid_attempts_month)&&Number.isInteger(d.llm_max_paid_attempts_per_month))text+=`・今月 ${d.llm_paid_attempts_month}/${d.llm_max_paid_attempts_per_month}`;if(d.llm_monthly_budget_exhausted)text+='・今月上限到達';if((d.llm_review_failures||0)>0)text+=`・失敗 ${d.llm_review_failures}件`;}
  if(Number.isFinite(h)&&h>24)text+=` / データ更新から${Math.floor(h)}時間`;
  if(serverPool<USER_STOCK_TARGET)text+=` / 100件未満のため自動補充モード`;
  const warn=d.provider_configured===false||d.llm_provider_configured===false||(d.query_success||0)<(d.query_total||0)||(d.llm_review_failures||0)>0||d.llm_monthly_budget_exhausted===true||(Number.isFinite(h)&&h>24)||serverPool<USER_STOCK_TARGET||available<USER_STOCK_TARGET;
  $('#sourceHealth').textContent=text;$('#sourceHealth').classList.toggle('warnText',warn);
}

async function loadFeed(){
  const r=await fetch(`./data/jobs.json?v=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);
  const d=await r.json();
  state.meta=d;
  const policyActive=Number(d.candidate_quality_policy_version||0)>=QUALITY_POLICY_VERSION&&d.candidate_quality_gate===QUALITY_GATE;
  const aiPolicyActive=Number(d.candidate_ai_tool_policy_gate_version||0)>=AI_TOOL_POLICY_GATE_VERSION&&d.candidate_rejects_explicit_ai_tool_bans===true;
  const serverRows=Array.isArray(d.jobs)?d.jobs:[];
  state.jobs=mergeCandidateStock(serverRows,policyActive,aiPolicyActive);
  updateHealth(d);resetWindow();render();
}
async function boot(){try{await loadFeed()}catch(e){$('#jobs').innerHTML='<div class="empty"><b>求人データを読み込めませんでした。</b><br>下の「Indeedで今すぐ検索」は利用できます。</div>';$('#countAvailable').textContent='0';$('#countHigh').textContent='0';$('#todayApplied').textContent=`${todayAppliedCount()}/${DAILY_TARGET}`;$('#updated').textContent='-';}}

$('#search').addEventListener('input',e=>{state.q=e.target.value;resetWindow();render()});
$('#openIndeed').onclick=()=>{const q=$('#search').value.trim()||'("完全在宅" OR "フルリモート") ("データ入力" OR アノテーション OR "AIトレーナー" OR "文字起こし" OR 校正 OR "商品登録")';const u=new URL('https://jp.indeed.com/jobs');u.searchParams.set('q',q);u.searchParams.set('l','在宅');u.searchParams.set('sort','date');u.searchParams.set('fromage','7');window.open(u.toString(),'_blank','noopener');};
$('#chips').addEventListener('click',e=>{const b=e.target.closest('.chip');if(!b)return;document.querySelectorAll('.chip[data-mode]').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.mode=b.dataset.mode;resetWindow();render();});
$('#sort').addEventListener('change',e=>{state.sort=e.target.value;resetWindow();render()});
$('#refreshFeed').onclick=async()=>{const b=$('#refreshFeed');b.disabled=true;b.textContent='読込中…';try{await loadFeed()}catch{}finally{b.disabled=false;b.textContent='最新候補を再読込';}};
if('serviceWorker' in navigator)navigator.serviceWorker.register('./sw.js').catch(()=>{});
boot();