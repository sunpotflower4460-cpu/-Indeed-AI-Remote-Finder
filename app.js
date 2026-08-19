const $=s=>document.querySelector(s);

function loadSet(key){
  try{const v=JSON.parse(localStorage.getItem(key)||'[]');return new Set(Array.isArray(v)?v.map(String):[])}catch{return new Set()}
}
function loadMap(key){
  try{const v=JSON.parse(localStorage.getItem(key)||'{}');return v&&typeof v==='object'&&!Array.isArray(v)?v:{}}catch{return{}}
}
function persistSet(key,value){try{localStorage.setItem(key,JSON.stringify([...value]))}catch{}}
function persistMap(key,value){try{localStorage.setItem(key,JSON.stringify(value))}catch{}}

const state={
  jobs:[],mode:'all',q:'',sort:'best',meta:{},
  saved:loadSet('savedJobs'),hidden:loadSet('hiddenJobs'),applied:loadSet('appliedJobs'),
  appliedAt:loadMap('appliedAt')
};

function esc(s=''){return String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function parseDate(s){if(!s)return null;const d=new Date(s);return Number.isNaN(+d)?null:d;}
function fmtDate(s){const d=parseDate(s);if(!d)return'不明';return new Intl.DateTimeFormat('ja-JP',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(d)}
function ageDays(s){const d=parseDate(s);if(!d)return null;return Math.max(0,(Date.now()-d.getTime())/864e5);}
function ageHours(s){const d=parseDate(s);if(!d)return null;return Math.max(0,(Date.now()-d.getTime())/36e5);}
function ageLabel(s){const h=ageHours(s);if(h===null)return'日付不明';if(h<24)return`${Math.max(1,Math.round(h))}時間以内`;return`${Math.floor(h/24)}日前目安`;}
function meterClass(v){return v>=82?'good':v>=64?'warn':'bad'}
function effectiveTier(j){const age=ageDays(j.search_published_at);if(age!==null&&age>30)return'expired';if(j.tier==='high'&&(age===null||age>14))return'review';return j.tier||'review';}
function feedAgeHours(){return ageHours(state.meta.generated_at);}
function hasDualPass(j){return effectiveTier(j)==='high'&&j.llm_strict_pass===true;}
function isNew(j){const h=ageHours(j.first_seen);return !j.carryover&&h!==null&&h<=36;}
function dateKey(d=new Date()){return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
function todayAppliedCount(){const today=dateKey();return Object.values(state.appliedAt).filter(v=>String(v).startsWith(today)).length;}

function candidateAvailable(j){
  const tier=effectiveTier(j);
  return tier!=='expired'&&!state.hidden.has(String(j.id))&&!state.applied.has(String(j.id));
}

function currentRows(){
  const q=state.q.trim().toLowerCase();
  let rows=state.jobs.filter(j=>{
    const id=String(j.id),tier=effectiveTier(j),isHidden=state.hidden.has(id),isSaved=state.saved.has(id),isApplied=state.applied.has(id);
    if(state.mode==='hidden')return isHidden;
    if(state.mode==='applied')return isApplied&&!isHidden;
    if(state.mode==='saved')return isSaved&&!isHidden;
    if(isHidden||isApplied||tier==='expired')return false;
    if(state.mode==='dual')return hasDualPass(j);
    if(state.mode==='high')return tier==='high';
    if(state.mode==='review')return tier==='review';
    return true;
  });
  if(q)rows=rows.filter(j=>`${j.title} ${j.company||''} ${j.location||''} ${j.snippet||''} ${(j.tags||[]).join(' ')} ${(j.automation_reasons||[]).join(' ')} ${j.llm_review?.automation_summary||''} ${(j.llm_review?.automation_plan||[]).join(' ')}`.toLowerCase().includes(q));
  rows=[...rows];
  if(state.sort==='fresh')rows.sort((a,b)=>(+parseDate(b.search_published_at)||0)-(+parseDate(a.search_published_at)||0)||(b.score||0)-(a.score||0));
  else if(state.sort==='auto')rows.sort((a,b)=>(b.automation_confidence||0)-(a.automation_confidence||0)||(b.remote_confidence||0)-(a.remote_confidence||0));
  else if(state.sort==='llm')rows.sort((a,b)=>(b.llm_review?.automatable_fraction??-1)-(a.llm_review?.automatable_fraction??-1)||(b.llm_review?.confidence??-1)-(a.llm_review?.confidence??-1));
  else rows.sort((a,b)=>{
    const rank={high:0,review:1,expired:2,hidden:3};
    return (hasDualPass(b)?1:0)-(hasDualPass(a)?1:0)
      ||(rank[effectiveTier(a)]??9)-(rank[effectiveTier(b)]??9)
      ||(isNew(b)?1:0)-(isNew(a)?1:0)
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
  const verdict={strong:'強い候補',uncertain:'不確定',reject:'不適合'}[r.verdict]||r.verdict,strict=j.llm_strict_pass===true;
  return `<details class="llmBox" ${strict?'open':''}><summary>${strict?'◎ LLM二重審査通過':'LLM二次審査'} · 技術代替 ${esc(r.automatable_fraction)}% · 確信 ${esc(r.confidence)}%</summary><div class="llmGrid"><div><span>判定</span><b>${esc(verdict)}</b></div><div><span>人間依存</span><b>${esc(r.human_dependency)}</b></div><div><span>同期対応</span><b>${esc(r.synchronous_human_interaction)}</b></div><div><span>データ注意</span><b>${esc(r.data_sensitivity_risk)}</b></div></div>${r.automation_summary?`<p>${esc(r.automation_summary)}</p>`:''}${r.automation_plan?.length?`<div class="llmSection"><b>自動化レシピ</b><ol>${listItems(r.automation_plan)}</ol></div>`:''}${r.blockers?.length?`<div class="llmSection risk"><b>技術的ブロッカー</b><ul>${listItems(r.blockers)}</ul></div>`:''}${r.questions_to_confirm?.length?`<div class="llmSection"><b>応募後に確認</b><ul>${listItems(r.questions_to_confirm)}</ul></div>`:''}</details>`;
}

function updateStats(){
  const available=state.jobs.filter(candidateAvailable).length;
  const high=state.jobs.filter(j=>candidateAvailable(j)&&effectiveTier(j)==='high').length;
  $('#countPool').textContent=available;
  $('#countHigh').textContent=high;
  $('#todayApplied').textContent=`${todayAppliedCount()}/10`;
  $('#updated').textContent=fmtDate(state.meta.generated_at);
}

function render(){
  updateStats();
  const rows=currentRows();
  $('#resultCount').textContent=`${rows.length}件`;
  const names={high:'高確度だけ',dual:'LLM二重審査済み',review:'次点候補',all:'おすすめ候補',saved:'保存済み',applied:'応募済み',hidden:'非表示'};
  $('#listTitle').textContent=names[state.mode]||'求人候補';
  if(!rows.length){
    $('#jobs').innerHTML=`<div class="empty"><b>この条件では候補がありません。</b><br>${state.mode==='all'?'次回の自動補充で新しい候補を追加します。':'「おすすめ候補」に戻すと次点候補まで確認できます。'}</div>`;
    return;
  }
  $('#jobs').innerHTML=rows.map(j=>{
    const id=String(j.id),saved=state.saved.has(id),hidden=state.hidden.has(id),applied=state.applied.has(id),tier=effectiveTier(j),high=tier==='high',dual=hasDualPass(j),published=j.search_published_at||j.last_seen,org=[j.company,j.location].filter(Boolean).map(esc).join(' · ');
    return `<article class="card ${high?'high':''} ${dual?'dualCard':''} ${tier==='expired'?'expired':''}"><div class="cardHead"><div class="verdict ${dual?'dualBadge':high?'ok':tier==='expired'?'expiredBadge':'review'}">${dual?'◎ 二重審査通過':verdictText(tier)}</div><div class="fresh">${esc(ageLabel(published))}</div></div><h3>${esc(j.title)}</h3>${org?`<div class="org">${org}</div>`:''}<p class="snippet">${esc(j.snippet||'求人概要なし')}</p><div class="scores"><div><span>AI代替</span><b class="${meterClass(j.automation_confidence)}">${j.automation_confidence??'-'}</b></div><div><span>完全在宅</span><b class="${meterClass(j.remote_confidence)}">${j.remote_confidence??'-'}</b></div><div><span>新しさ</span><b class="${meterClass(j.freshness_confidence)}">${j.freshness_confidence??'-'}</b></div></div><div class="why">${esc(reasonText(j))}</div><div class="tags">${isNew(j)?'<span class="tag newTag">NEW</span>':''}${(j.tags||[]).slice(0,5).map(t=>`<span class="tag">${esc(t)}</span>`).join('')}${j.seen_count>1?`<span class="tag repeat">再検出 ${j.seen_count}回</span>`:''}${j.duplicate_count>1?`<span class="tag">類似掲載 ${j.duplicate_count}件を統合</span>`:''}${j.carryover?'<span class="tag carry">予備候補・今回未再検出</span>':''}${dual?'<span class="tag dualTag">LLM二重審査 ✓</span>':''}${applied?'<span class="tag appliedTag">応募済み</span>':''}</div>${j.risk_reasons?.length?`<div class="risk">要注意: ${esc(j.risk_reasons.join('・'))}</div>`:''}${llmPanel(j)}${j.carryover?'<div class="reserveNote">予備候補です。最新スキャンでは未再検出のため、リンク先で募集継続を確認してください。</div>':''}<div class="actions"><button class="btn ghost save" data-id="${esc(id)}">${saved?'★ 保存済み':'☆ 保存'}</button><button class="btn ghost applied" data-id="${esc(id)}">${applied?'↩ 未応募に戻す':'✓ 応募済みにする'}</button><button class="btn ghost hide" data-id="${esc(id)}">${hidden?'↩ 戻す':'× 非表示'}</button><a class="btn primary" href="${esc(j.url)}" target="_blank" rel="noopener noreferrer">求人を確認・応募 →</a></div><div class="meta">掲載目安: ${esc(j.posted_label||fmtDate(j.search_published_at))} / 最終検出: ${esc(fmtDate(j.last_seen))}${j.llm_model?` / LLM: ${esc(j.llm_model)}`:''}</div></article>`;
  }).join('');

  document.querySelectorAll('.save').forEach(b=>b.onclick=()=>{const id=b.dataset.id;if(state.saved.has(id))state.saved.delete(id);else state.saved.add(id);persistSet('savedJobs',state.saved);render();});
  document.querySelectorAll('.hide').forEach(b=>b.onclick=()=>{const id=b.dataset.id;if(state.hidden.has(id))state.hidden.delete(id);else state.hidden.add(id);persistSet('hiddenJobs',state.hidden);render();});
  document.querySelectorAll('.applied').forEach(b=>b.onclick=()=>{
    const id=b.dataset.id;
    if(state.applied.has(id)){
      state.applied.delete(id);delete state.appliedAt[id];
    }else{
      state.applied.add(id);state.saved.add(id);state.appliedAt[id]=`${dateKey()}T${new Date().toTimeString().slice(0,8)}`;
    }
    persistSet('appliedJobs',state.applied);persistSet('savedJobs',state.saved);persistMap('appliedAt',state.appliedAt);render();
  });
}

function updateHealth(d){
  const h=feedAgeHours();
  let text=d.provider_configured===false?'求人自動更新はSERPAPI_KEY設定後に有効':`候補プール ${d.candidate_pool_size??state.jobs.length}件`;
  if(Number.isInteger(d.new_jobs))text+=`・新着 ${d.new_jobs}件`;
  if(Number.isInteger(d.live_jobs))text+=`・今回検出 ${d.live_jobs}件`;
  if(Number.isInteger(d.carryover_jobs)&&d.carryover_jobs>0)text+=`・予備 ${d.carryover_jobs}件`;
  if(d.query_total)text+=` / 自動検索 ${d.query_success||0}/${d.query_total}`;
  if(d.serpapi_bootstrap_mode||d.pool_under_target)text+=' / 30件未満のため補充モード';
  if(Number.isInteger(d.serpapi_search_attempts_month)&&Number.isInteger(d.serpapi_max_search_attempts_per_month))text+=` / 検索枠 ${d.serpapi_search_attempts_month}/${d.serpapi_max_search_attempts_per_month}`;
  if(d.llm_provider_configured===true)text+=` / LLM審査 ${d.llm_reviewed_jobs||0}件・二重通過 ${d.llm_strict_jobs||0}件`;
  if((d.llm_review_failures||0)>0)text+=`・LLM失敗 ${d.llm_review_failures}件`;
  if(Number.isFinite(h)&&h>24)text+=` / データ更新から${Math.floor(h)}時間`;
  const warn=d.provider_configured===false||d.pool_under_target===true||(d.query_success||0)<(d.query_total||0)||(d.llm_review_failures||0)>0||d.serpapi_monthly_budget_exhausted===true||(Number.isFinite(h)&&h>24);
  $('#sourceHealth').textContent=text;$('#sourceHealth').classList.toggle('warnText',warn);
}

async function boot(){
  try{
    const r=await fetch(`./data/jobs.json?v=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);
    const d=await r.json();state.jobs=Array.isArray(d.jobs)?d.jobs:[];state.meta=d;updateHealth(d);render();
  }catch(e){
    $('#jobs').innerHTML='<div class="empty"><b>求人データを読み込めませんでした。</b><br>下の「Indeedで今すぐ検索」は利用できます。</div>';
    $('#countPool').textContent='0';$('#countHigh').textContent='0';$('#todayApplied').textContent=`${todayAppliedCount()}/10`;$('#updated').textContent='-';
  }
}

$('#search').addEventListener('input',e=>{state.q=e.target.value;render()});
$('#openIndeed').onclick=()=>{const q=$('#search').value.trim()||'("完全在宅" OR "フルリモート") ("データ入力" OR アノテーション OR "AIトレーナー" OR "文字起こし" OR 校正 OR "商品登録")';const u=new URL('https://jp.indeed.com/jobs');u.searchParams.set('q',q);u.searchParams.set('l','在宅');u.searchParams.set('sort','date');u.searchParams.set('fromage','14');window.open(u.toString(),'_blank','noopener');};
$('#reloadPool').onclick=async()=>{const b=$('#reloadPool');b.disabled=true;b.textContent='読込中…';await boot();b.disabled=false;b.textContent='最新候補を読み直す';};
$('#chips').addEventListener('click',e=>{const b=e.target.closest('.chip');if(!b)return;document.querySelectorAll('.chip[data-mode]').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.mode=b.dataset.mode;render();});
$('#sort').addEventListener('change',e=>{state.sort=e.target.value;render()});
if('serviceWorker' in navigator)navigator.serviceWorker.register('./sw.js').catch(()=>{});
boot();
