const state={jobs:[],mode:'high',q:'',sort:'best',saved:new Set(JSON.parse(localStorage.getItem('savedJobs')||'[]')),meta:{}};
const $=s=>document.querySelector(s);
function esc(s=''){return String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function fmtDate(s){if(!s)return'不明';const d=new Date(s);if(Number.isNaN(+d))return'不明';return new Intl.DateTimeFormat('ja-JP',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(d)}
function ageLabel(s){if(!s)return'日付不明';const d=new Date(s);if(Number.isNaN(+d))return'日付不明';const h=Math.max(0,(Date.now()-d)/36e5);if(h<24)return`${Math.max(1,Math.round(h))}時間以内`;const days=Math.round(h/24);return`${days}日前目安`;}
function meterClass(v){return v>=82?'good':v>=64?'warn':'bad'}
function currentRows(){
  const q=state.q.trim().toLowerCase();
  let rows=state.jobs.filter(j=>state.mode==='saved'?state.saved.has(j.id):state.mode==='all'?true:j.tier===state.mode);
  if(q)rows=rows.filter(j=>`${j.title} ${j.snippet} ${(j.tags||[]).join(' ')} ${(j.automation_reasons||[]).join(' ')}`.toLowerCase().includes(q));
  rows=[...rows];
  if(state.sort==='fresh')rows.sort((a,b)=>(b.freshness_confidence||0)-(a.freshness_confidence||0)||(b.score||0)-(a.score||0));
  else if(state.sort==='auto')rows.sort((a,b)=>(b.automation_confidence||0)-(a.automation_confidence||0)||(b.remote_confidence||0)-(a.remote_confidence||0));
  else rows.sort((a,b)=>(a.tier==='high'?0:1)-(b.tier==='high'?0:1)||(b.score||0)-(a.score||0)||(b.freshness_confidence||0)-(a.freshness_confidence||0));
  return rows;
}
function reasonText(j){const r=(j.automation_reasons||[]).slice(0,4);return r.length?`AI化しやすい根拠: ${r.join('・')}`:'仕事内容の詳細確認が必要';}
function render(){
  const rows=currentRows();
  $('#resultCount').textContent=`${rows.length}件`;
  const names={high:'高確度だけ',review:'要確認候補',all:'全候補',saved:'保存済み'};
  $('#listTitle').textContent=names[state.mode]||'求人候補';
  if(!rows.length){$('#jobs').innerHTML=`<div class="empty"><b>この条件では候補がありません。</b><br>品質を落として無理に表示していません。<br><span>「要確認候補」か「Indeedで今すぐ検索」を使えます。</span></div>`;return;}
  $('#jobs').innerHTML=rows.map(j=>{
    const saved=state.saved.has(j.id), high=j.tier==='high';
    const published=j.search_published_at||j.last_seen;
    return `<article class="card ${high?'high':''}">
      <div class="cardHead"><div class="verdict ${high?'ok':'review'}">${high?'高確度':'要確認'}</div><div class="fresh">${esc(ageLabel(published))}</div></div>
      <h3>${esc(j.title)}</h3>
      <p class="snippet">${esc(j.snippet||'検索スニペットなし')}</p>
      <div class="scores">
        <div><span>AI代替</span><b class="${meterClass(j.automation_confidence)}">${j.automation_confidence??'-'}</b></div>
        <div><span>完全在宅</span><b class="${meterClass(j.remote_confidence)}">${j.remote_confidence??'-'}</b></div>
        <div><span>新しさ</span><b class="${meterClass(j.freshness_confidence)}">${j.freshness_confidence??'-'}</b></div>
      </div>
      <div class="why">${esc(reasonText(j))}</div>
      <div class="tags">${(j.tags||[]).slice(0,5).map(t=>`<span class="tag">${esc(t)}</span>`).join('')}${j.seen_count>1?`<span class="tag repeat">再検出 ${j.seen_count}回</span>`:''}</div>
      ${j.risk_reasons?.length?`<div class="risk">要注意: ${esc(j.risk_reasons.join('・'))}</div>`:''}
      <div class="actions"><button class="btn ghost save" data-id="${esc(j.id)}">${saved?'★ 保存済み':'☆ 保存'}</button><a class="btn primary" href="${esc(j.url)}" target="_blank" rel="noopener noreferrer">求人を確認・応募 →</a></div>
      <div class="meta">検索上の日時: ${esc(fmtDate(j.search_published_at))} / 最終検出: ${esc(fmtDate(j.last_seen))}</div>
    </article>`;
  }).join('');
  document.querySelectorAll('.save').forEach(b=>b.onclick=()=>{const id=b.dataset.id;if(state.saved.has(id))state.saved.delete(id);else state.saved.add(id);localStorage.setItem('savedJobs',JSON.stringify([...state.saved]));render();});
}
async function boot(){
  try{
    const r=await fetch(`./data/jobs.json?v=${Date.now()}`,{cache:'no-store'}); if(!r.ok)throw new Error(`HTTP ${r.status}`);
    const d=await r.json();state.jobs=d.jobs||[];state.meta=d;
    const high=state.jobs.filter(j=>j.tier==='high').length, review=state.jobs.filter(j=>j.tier==='review').length;
    $('#countHigh').textContent=high;$('#countReview').textContent=review;$('#updated').textContent=fmtDate(d.generated_at);
    $('#sourceHealth').textContent=d.query_total?`検索取得 ${d.query_success||0}/${d.query_total}`:'検索取得 -';
    if((d.query_success||0)<(d.query_total||0))$('#sourceHealth').classList.add('warnText');
    render();
  }catch(e){$('#jobs').innerHTML='<div class="empty"><b>求人データを読み込めませんでした。</b><br>下の「Indeedで今すぐ検索」は利用できます。</div>';$('#countHigh').textContent='0';$('#countReview').textContent='0';$('#updated').textContent='-';}
}
$('#search').addEventListener('input',e=>{state.q=e.target.value;render()});
$('#openIndeed').onclick=()=>{const q=$('#search').value.trim()||'("完全在宅" OR "フルリモート") ("データ入力" OR アノテーション OR "AIトレーナー" OR "文字起こし" OR 校正 OR "商品登録")';const u=new URL('https://jp.indeed.com/jobs');u.searchParams.set('q',q);u.searchParams.set('l','在宅');u.searchParams.set('sort','date');u.searchParams.set('fromage','7');window.open(u.toString(),'_blank','noopener');};
$('#chips').addEventListener('click',e=>{const b=e.target.closest('.chip');if(!b)return;document.querySelectorAll('.chip[data-mode]').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.mode=b.dataset.mode;render();});
$('#sort').addEventListener('change',e=>{state.sort=e.target.value;render()});
if('serviceWorker' in navigator)navigator.serviceWorker.register('./sw.js').catch(()=>{});
boot();
