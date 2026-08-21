(()=>{
  'use strict';

  const JAPANESE_RE=/[ぁ-んァ-ヶ一-龯]/;
  const sourceApi=()=>window.__jobSourceTabs||{};

  function safeIndeed(value){
    try{
      const url=new URL(String(value||''));
      const host=url.hostname.toLowerCase();
      if(url.protocol!=='https:'||!(host==='indeed.com'||host.endsWith('.indeed.com')))return null;
      if(url.pathname.toLowerCase()!=='/viewjob'||!url.searchParams.get('jk'))return null;
      return url;
    }catch{return null;}
  }

  function cleanOriginalTitle(value){
    return String(value||'')
      .replace(/\s*[-|–—]\s*(job post\s*[-|–—]\s*)?Indeed(?:\.com)?\s*$/i,'')
      .replace(/\s*[-|–—]\s*(求人|採用情報)\s*$/,'')
      .replace(/\s+/g,' ')
      .trim();
  }

  function profileJa(value){
    const key=String(value||'').replace(/^search-vjk-/,'').toLowerCase();
    const pairs=[
      [/senior-rater/,'シニアレイター'],[/quality-assurance-rater/,'品質評価レイター'],
      [/rater|evaluator/,'AI評価・レイター'],[/ai-trainer/,'AIトレーナー'],
      [/annotation/,'データアノテーション'],[/data-label/,'データラベリング'],
      [/translation/,'翻訳・文章チェック'],[/proofread/,'校正・文章チェック'],
      [/localization/,'ローカライズ'],[/transcription/,'文字起こし'],
      [/search-quality|search-evaluation/,'検索品質評価'],[/data-entry/,'データ入力'],
      [/telus/,'TELUS レイター'],[/dataannotation/,'DataAnnotation AIトレーナー'],
      [/remote-ai|ai-general/,'AI関連・完全在宅']
    ];
    return pairs.find(([re])=>re.test(key))?.[1]||'Indeed求人候補';
  }

  function japaneseRoleTitle(value,profile=''){
    const title=cleanOriginalTitle(value);
    if(title&&JAPANESE_RE.test(title)&&!/^[\s\S]{0,8}\b(japanese|remote)\b/i.test(title))return title;
    const text=`${title} ${profile}`.toLowerCase();
    const rules=[
      [/senior\s+rater/,'シニアレイター（AI生成コンテンツ評価）'],
      [/quality\s+assurance\s+rater/,'品質評価レイター'],
      [/ai\s+language\s+expert.*japanese|japanese.*ai\s+language\s+expert/,'日本語AI言語評価スタッフ'],
      [/japanese\s+language\s+expert/,'日本語・言語品質評価スタッフ'],
      [/ai\s+trainer\s+specialist/,'AIトレーナー・評価スタッフ'],
      [/ai\s+trainer|aiトレーナー/,'AIトレーナー'],
      [/generalist\s+data\s+annotator|data\s+annotator|annotation|annotator/,'データアノテーションスタッフ'],
      [/data\s+label|labeling|labelling/,'データラベリングスタッフ'],
      [/translator|translation|翻訳/,'日本語翻訳・文章チェック'],
      [/proofread|校正/,'校正・文章チェック'],
      [/localization|localisation|ローカライズ/,'日本語ローカライズ・品質チェック'],
      [/transcription|文字起こし/,'文字起こし・データ整理'],
      [/search\s+quality|search\s+evaluation|map\s+quality|maps|relevance/,'検索・地図品質評価スタッフ'],
      [/rater|evaluator|evaluation|ai評価|品質評価/,'AI回答・品質評価スタッフ'],
      [/language\s+expert|linguist|language\s+specialist/,'日本語・言語品質評価スタッフ'],
      [/coding|software|programming|developer|engineer/,'コーディング・技術AI評価スタッフ']
    ];
    const matched=rules.find(([re])=>re.test(text));
    return matched?.[1]||profileJa(profile);
  }

  function japanesePriority(job){
    if(!job)return 0;
    const title=String(job.title||'');
    const snippet=String(job.snippet||'').slice(0,1400);
    const location=String(job.location||'');
    let score=0;
    if(JAPANESE_RE.test(title))score+=100;
    if(job.japan_eligibility_status==='japan-explicit')score+=60;
    if(/japan|日本|tokyo|東京/i.test(location))score+=35;
    const jaChars=(snippet.match(/[ぁ-んァ-ヶ一-龯]/g)||[]).length;
    if(jaChars>=60)score+=30;else if(jaChars>=15)score+=15;
    if(/japanese|日本語/i.test(title))score+=12;
    if(job.japan_eligibility_status==='worldwide-explicit')score+=5;
    return score;
  }

  const previousCurrentRows=currentRows;
  currentRows=function(){
    const rows=previousCurrentRows();
    if(sourceApi().mode!=='other')return rows;
    return [...rows].sort((a,b)=>
      japanesePriority(b)-japanesePriority(a)
      ||(Number(b.score)||0)-(Number(a.score)||0)
      ||(+parseDate(freshnessReference(b))||0)-(+parseDate(freshnessReference(a))||0)
    );
  };

  function seedKind(seed){
    return String(seed?.indeed_index_link_kind||'viewjob-jk')==='search-vjk'?'search-vjk':'viewjob-jk';
  }

  function candidateSeeds(){
    const raw=Array.isArray(state.meta?.candidate_indeed_index_seeds)?state.meta.candidate_indeed_index_seeds:[];
    const byJk=new Map();
    for(const seed of raw){
      const url=safeIndeed(seed?.url);
      if(!seed||!url)continue;
      const jk=String(seed.jk||url.searchParams.get('jk')||'').trim();
      if(!jk)continue;
      const old=byJk.get(jk);
      if(!old||seedKind(seed)==='viewjob-jk')byJk.set(jk,{...seed,jk,url:url.toString()});
    }
    const finalByJk=new Map();
    for(const job of state.jobs||[]){
      if(!job||String(job.apply_source_kind||'').toLowerCase()!=='indeed')continue;
      const url=safeIndeed(job.url);
      if(!url)continue;
      const jk=String(url.searchParams.get('jk')||job.id||'').trim();
      if(jk)finalByJk.set(jk,job);
      if(jk&&!byJk.has(jk)){
        byJk.set(jk,{
          jk,url:url.toString(),title:job.title||'',snippet:'',profile:'',last_seen:job.last_seen||state.meta?.generated_at,
          indeed_index_link_kind:'viewjob-jk',indeed_exact_url_verified:true
        });
      }
    }
    return [...byJk.values()].map(seed=>({...seed,finalJob:finalByJk.get(String(seed.jk))||null}));
  }

  function activeCategory(){
    const node=document.querySelector('#uxCategoryBar [data-category].active, #uxCategoryBar .active[data-category]');
    return String(node?.dataset?.category||'all');
  }

  function evidenceCategory(item){
    const text=`${item.seed?.title||item.title||''} ${item.profile||''} ${item.finalJob?.title||''}`.toLowerCase();
    if(/coding|software|programming|developer|engineer|数学|physics|chemistry|biology/.test(text))return'technical';
    if(/translation|translator|proofread|localization|language|linguist|翻訳|校正|言語/.test(text))return'language';
    if(/annotat|label|data entry|transcription|アノテーション|ラベル|データ入力|文字起こし/.test(text))return'data';
    if(/rater|evaluator|evaluation|search|quality|ai trainer|ai-trainer|評価|検索品質/.test(text))return'evaluation';
    return'other';
  }

  function modeAllows(id){
    const declined=state.declined.has(id),applied=state.applied.has(id),favorite=state.favorite.has(id);
    if(state.mode==='declined')return declined;
    if(state.mode==='applied')return applied&&!declined;
    if(state.mode==='favorite')return favorite&&!declined;
    return !declined&&!applied;
  }

  function filteredIndeedCandidates(){
    let rows=candidateSeeds().filter(item=>modeAllows(String(item.jk)));
    const q=String(state.q||'').trim().toLowerCase();
    if(q){
      rows=rows.filter(item=>`${item.title||''} ${item.profile||''} ${item.snippet||''} ${item.finalJob?.title||''} ${item.finalJob?.company||''}`.toLowerCase().includes(q));
    }
    const category=activeCategory();
    if(category&&category!=='all')rows=rows.filter(item=>evidenceCategory(item)===category);
    rows.sort((a,b)=>
      (b.finalJob?1:0)-(a.finalJob?1:0)
      ||(seedKind(a)==='viewjob-jk'?0:1)-(seedKind(b)==='viewjob-jk'?0:1)
      ||(+parseDate(b.last_seen)||0)-(+parseDate(a.last_seen)||0)
    );
    return rows;
  }

  function escHtml(value){
    return String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }

  function seedCard(item){
    const job=item.finalJob;
    const isVjk=seedKind(item)==='search-vjk';
    const id=String(item.jk||'');
    const original=cleanOriginalTitle(job?.title||item.title||'');
    const display=japaneseRoleTitle(original,item.profile||'');
    const company=String(job?.company||'').trim();
    const status=job
      ?'AI代替適性まで確認済み'
      :isVjk?'求人ID確認済み（vjk）':'Indeed実URL確認済み';
    const substatus=job
      ?'別ソースの仕事内容とIndeedの会社・求人を照合済み。Indeed本文はバックエンドでは未自動取得です。'
      :isVjk
        ?'Indeed検索ページ上の求人IDを確認。個別URLはIDから生成しているため、開いて本文を確認してください。'
        :'Indeed個別求人URLを公開インデックスで確認済み。AI代替適性はまだ審査前です。';
    const age=typeof ageLabel==='function'?ageLabel(item.last_seen):'最近確認';
    const favorite=state.favorite.has(id),applied=state.applied.has(id),declined=state.declined.has(id);
    return `<article class="card sourceLeadCard ${job?'sourceLeadVerified':''} ${isVjk?'sourceLeadVjk':''}" data-seed-id="${escHtml(id)}">
      <div class="sourceLeadTop"><span class="sourceLeadStatus">${escHtml(status)}</span><span class="fresh">${escHtml(age)}</span></div>
      <h3>${escHtml(display)}</h3>
      ${company?`<div class="uxCompany">${escHtml(company)} · 日本から確認</div>`:''}
      ${original&&original!==display?`<div class="sourceLeadOriginal">原題：${escHtml(original)}</div>`:''}
      <p class="uxSummary">${escHtml(substatus)}</p>
      <div class="uxTags">
        <span>Indeed</span><span>${isVjk?'求人ID確認':'個別URL確認'}</span>${job?'<span>AI適性確認済み</span>':'<span>AI適性は未確認</span>'}
      </div>
      <div class="uxDestinations"><a class="btn primary sourceLeadOpen" href="${escHtml(item.url)}" target="_blank" rel="noopener noreferrer">${isVjk?'Indeedで候補本文を確認':'Indeedで求人を見る'} →</a></div>
      <div class="uxActions sourceLeadActions">
        <button class="btn ghost sourceSeedFavorite" data-id="${escHtml(id)}">${favorite?'★ 保存済み':'☆ 保存'}</button>
        <button class="btn ghost sourceSeedApplied" data-id="${escHtml(id)}">${applied?'↩ 応募済み解除':'✓ 応募済み'}</button>
        <button class="btn ghost sourceSeedDecline" data-id="${escHtml(id)}">${declined?'↩ 戻す':'× 除外'}</button>
      </div>
    </article>`;
  }

  function bindSeedActions(){
    document.querySelectorAll('#jobs .sourceSeedFavorite').forEach(button=>button.onclick=()=>{
      const id=String(button.dataset.id||'');
      if(state.favorite.has(id))state.favorite.delete(id);else state.favorite.add(id);
      persistSet('savedJobs',state.favorite);render();
    });
    document.querySelectorAll('#jobs .sourceSeedApplied').forEach(button=>button.onclick=()=>{
      const id=String(button.dataset.id||'');
      if(state.applied.has(id)){
        state.applied.delete(id);delete state.appliedAt[id];
      }else{
        state.applied.add(id);state.declined.delete(id);state.appliedAt[id]=new Date().toISOString();
      }
      persistSet('appliedJobs',state.applied);persistSet('declinedJobs',state.declined);persistMap('appliedAt',state.appliedAt);render();
    });
    document.querySelectorAll('#jobs .sourceSeedDecline').forEach(button=>button.onclick=()=>{
      const id=String(button.dataset.id||'');
      if(state.declined.has(id))state.declined.delete(id);else{state.declined.add(id);state.applied.delete(id);delete state.appliedAt[id];}
      persistSet('declinedJobs',state.declined);persistSet('appliedJobs',state.applied);persistMap('appliedAt',state.appliedAt);render();
    });
  }

  function renderIndeedMain(){
    if(sourceApi().mode!=='indeed')return false;
    const rows=filteredIndeedCandidates();
    const jobs=document.querySelector('#jobs');
    if(!jobs)return false;
    const title=document.querySelector('#listTitle');
    const count=document.querySelector('#resultCount');
    if(title)title.textContent=state.mode==='favorite'?'保存したIndeed候補':state.mode==='applied'?'応募済みのIndeed候補':state.mode==='declined'?'除外したIndeed候補':'Indeedで見つけた求人候補';
    if(count)count.textContent=`${rows.length}件`;
    jobs.innerHTML=rows.length
      ?rows.map(seedCard).join('')
      :'<div class="empty"><b>この条件ではIndeed候補がありません。</b><br>上の「Indeed本体で検索」から現在のIndeed検索結果を直接確認できます。</div>';
    document.querySelector('#indeedSeedArea')?.classList.add('sourcePresentationDuplicateHidden');
    bindSeedActions();
    return true;
  }

  function otherJobMap(){return new Map((state.jobs||[]).filter(Boolean).map(job=>[String(job.id),job]));}

  function localizeOtherCards(){
    if(sourceApi().mode!=='other')return;
    const byId=otherJobMap();
    document.querySelectorAll('#jobs .uxCard').forEach(card=>{
      const id=String(card.querySelector('[data-id]')?.dataset.id||'');
      const job=byId.get(id);
      const heading=card.querySelector('h3');
      if(job&&heading)heading.textContent=japaneseRoleTitle(job.title,job.semantic_role_family||'');
      card.querySelectorAll('.uxAlt').forEach(alt=>{
        const altId=String(alt.querySelector('[data-id]')?.dataset.id||'');
        const altJob=byId.get(altId);
        const label=alt.querySelector('.uxAltMain b');
        if(altJob&&label)label.textContent=japaneseRoleTitle(altJob.title,altJob.semantic_role_family||'');
      });
    });
    const title=document.querySelector('#listTitle');
    if(title&&state.mode==='all')title.textContent='その他の求人サイト（日本語・日本向けを優先）';
  }

  function refreshSourceTabs(){
    const bar=document.querySelector('#uxSourceTabs');
    if(!bar)return;
    const raw=candidateSeeds();
    const exact=raw.filter(seed=>seedKind(seed)==='viewjob-jk').length;
    const vjk=raw.filter(seed=>seedKind(seed)==='search-vjk').length;
    const verified=raw.filter(seed=>Boolean(seed.finalJob)).length;
    const indeed=bar.querySelector('[data-source="indeed"]');
    if(indeed)indeed.textContent=`Indeed候補 ${raw.length}件（AI適性 ${verified} / 実URL ${exact} / 求人ID ${vjk}）`;
    const other=bar.querySelector('[data-source="other"]');
    if(other){
      const count=(state.jobs||[]).filter(job=>job&&isAvailable(job)&&!sourceApi().isVerifiedIndeed?.(job)).length;
      other.textContent=`その他の求人サイト ${count}件（日本語優先）`;
    }
  }

  const style=document.createElement('style');
  style.textContent=`
    .sourcePresentationDuplicateHidden{display:none!important}
    .sourceLeadCard{border-color:#214a64;background:linear-gradient(180deg,#0a1c2a 0%,#071522 100%)}
    .sourceLeadVerified{border-color:#54d6e7;box-shadow:inset 0 0 0 1px rgba(84,214,231,.08)}
    .sourceLeadVjk{border-style:dashed}
    .sourceLeadTop{display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:8px}
    .sourceLeadStatus{display:inline-flex;width:max-content;max-width:100%;border-radius:999px;padding:5px 8px;background:#102d3e;color:#86e7f2;font-size:9px;font-weight:850}
    .sourceLeadVerified .sourceLeadStatus{background:#14372f;color:#9cf0cf}
    .sourceLeadVjk .sourceLeadStatus{background:#30291a;color:#f0ce83}
    .sourceLeadOriginal{margin:-3px 0 8px;color:#7f9aac;font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .sourceLeadActions{margin-top:8px}
  `;
  document.head.appendChild(style);

  const previousRender=render;
  render=function(){
    previousRender();
    refreshSourceTabs();
    if(!renderIndeedMain())localizeOtherCards();
  };

  render();

  window.__sourcePresentation={japaneseRoleTitle,japanesePriority,candidateSeeds};
})();
