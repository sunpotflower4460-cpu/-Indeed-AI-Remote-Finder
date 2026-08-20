(()=>{
  'use strict';

  const UX_VERSION=1;
  let category='all';

  const FAMILY={
    coding:{label:'コーディング・開発',category:'technical',summary:'プログラムや技術課題を確認し、AIの回答を評価・改善する完全在宅の仕事です。'},
    specialist:{label:'専門分野のAI評価',category:'technical',summary:'数学・科学などの専門知識を使って、AIの回答や課題の正しさを評価する完全在宅の仕事です。'},
    localization:{label:'ローカライズ',category:'language',summary:'ゲームやコンテンツの日本語表現を確認し、翻訳・ローカライズ品質を整える完全在宅の仕事です。'},
    translation:{label:'翻訳・文章チェック',category:'language',summary:'翻訳、校正、機械翻訳の修正など、文章を中心に扱う完全在宅の仕事です。'},
    language:{label:'日本語・言語評価',category:'language',summary:'日本語の自然さや意味、AIが生成した文章の品質を評価する完全在宅の仕事です。'},
    annotation:{label:'データ分類・アノテーション',category:'data',summary:'データの分類、ラベル付け、内容確認など、繰り返し型のデジタル作業が中心の完全在宅の仕事です。'},
    search:{label:'検索・地図の品質評価',category:'evaluation',summary:'検索結果や地図情報が正しいか、基準に沿って評価する完全在宅の仕事です。'},
    evaluation:{label:'AI回答の評価',category:'evaluation',summary:'AIの回答を読み、正確さ・自然さ・品質などを基準に沿って評価する完全在宅の仕事です。'},
    other:{label:'その他のAI関連業務',category:'other',summary:'AIで補助しやすく、人が常時張り付く必要が少ない完全在宅の候補です。'},
  };

  function textFor(job){
    return `${job?.title||''} ${job?.semantic_role_family||''} ${(job?.tags||[]).join(' ')} ${(job?.automation_reasons||[]).join(' ')}`.toLowerCase();
  }

  function jobFamily(job){
    const text=textFor(job);
    if(/coding|software|programming|developer|engineer|code review|デバッグ|コーディング/.test(text))return'coding';
    if(/mathematics|physics|chemistry|biology|science|subject matter expert|domain expert|専門家|数学|物理|化学|生物/.test(text))return'specialist';
    if(/localization|localisation|ローカライズ|in-game/.test(text))return'localization';
    if(/translation|translator|post-editor|proofread|翻訳|校正/.test(text))return'translation';
    if(/annotat|labeling|labelling|data labeling|data classification|アノテーション|ラベル/.test(text))return'annotation';
    if(/search quality|search eval|maps|map quality|relevance|検索評価|検索品質|地図/.test(text))return'search';
    if(/linguist|language expert|japanese expert|language specialist|言語|日本語評価/.test(text))return'language';
    if(/ai trainer|ai rater|evaluator|evaluation|rating|quality assurance rater|ai評価|品質評価/.test(text))return'evaluation';
    return'other';
  }

  function familyInfo(job){return FAMILY[jobFamily(job)]||FAMILY.other;}

  function domainJa(title=''){
    const pairs=[
      [/mathematics/i,'数学'],[/physics/i,'物理'],[/chemistry/i,'化学'],[/biology/i,'生物'],
      [/finance|accounting/i,'金融・会計'],[/law|legal/i,'法律'],[/medicine|medical|health/i,'医療'],
      [/economics/i,'経済'],[/statistics/i,'統計'],[/computer science/i,'コンピューター科学'],
    ];
    return pairs.find(([re])=>re.test(title))?.[1]||'';
  }

  function titleJa(job){
    const title=String(job?.title||'').trim();
    if(/[ぁ-んァ-ヶ一-龯]/.test(title)&&!/^.{0,8}\b(japanese|ai|remote)\b/i.test(title))return title;
    const family=jobFamily(job);
    if(family==='coding')return'日本語コーディングAIトレーナー';
    if(family==='specialist'){
      const domain=domainJa(title);
      return domain?`${domain}分野のAI評価スタッフ`:'専門分野のAI評価スタッフ';
    }
    if(family==='localization')return'日本語ローカライズ・品質チェック';
    if(family==='translation')return'日本語翻訳・文章チェック';
    if(family==='annotation')return'日本語データアノテーション';
    if(family==='search')return'検索・地図品質評価スタッフ';
    if(family==='language')return'日本語・言語品質評価スタッフ';
    if(family==='evaluation')return'日本語AI評価スタッフ';
    return'AIで補助しやすい完全在宅ワーク';
  }

  function locationJa(job){
    if(job?.japan_eligibility_status==='japan-explicit')return'日本から応募可';
    if(job?.japan_eligibility_status==='worldwide-explicit')return'世界から応募可';
    const location=String(job?.location||'');
    if(/japan|日本|tokyo|東京/i.test(location))return'日本から応募可';
    if(/world|global|anywhere/i.test(location))return'世界から応募可';
    return'完全在宅';
  }

  function safeHttps(value){
    try{
      const url=new URL(String(value||''));
      return url.protocol==='https:'?url.toString():'';
    }catch{return'';}
  }

  function directIndeedUrl(job){
    const candidates=[job?.indeed_url,job?.indeed_listing_url,job?.apply_source_kind==='indeed'?job?.url:''];
    for(const value of candidates){
      const safe=safeHttps(value);
      if(!safe)continue;
      const url=new URL(safe);
      const host=url.hostname.toLowerCase();
      if((host==='indeed.com'||host.endsWith('.indeed.com'))&&url.pathname.toLowerCase().includes('/viewjob')&&url.searchParams.get('jk')){
        return `https://jp.indeed.com/viewjob?jk=${encodeURIComponent(url.searchParams.get('jk'))}`;
      }
    }
    return'';
  }

  function indeedSearchUrl(job){
    const url=new URL('https://jp.indeed.com/jobs');
    const company=String(job?.company||'').trim();
    const title=String(job?.title||'').replace(/\s*[–—-]\s*remote\b/ig,'').trim();
    url.searchParams.set('q',[company,title].filter(Boolean).join(' '));
    url.searchParams.set('l','在宅');
    url.searchParams.set('sort','date');
    return url.toString();
  }

  function indeedDestination(job){
    const direct=directIndeedUrl(job);
    return direct
      ?{url:direct,label:'Indeedで求人を見る',exact:true}
      :{url:indeedSearchUrl(job),label:'Indeedで同じ求人を探す',exact:false};
  }

  function officialUrl(job){
    const url=safeHttps(job?.url);
    if(!url)return'';
    try{
      const host=new URL(url).hostname.toLowerCase();
      if(host==='indeed.com'||host.endsWith('.indeed.com'))return'';
    }catch{}
    return url;
  }

  function statusTags(job){
    const tags=[locationJa(job),'張り付き少なめ'];
    if(job?.ai_tool_policy_status==='explicitly-allowed')tags.push('AI利用可の記載あり');
    else tags.push('AI利用は要確認');
    return tags.slice(0,3);
  }

  function detailStatus(value,type){
    if(type==='human')return{low:'少ない',medium:'一部あり',high:'多い'}[value]||'要確認';
    if(type==='sync')return{none:'なし',occasional:'一部あり',frequent:'多い'}[value]||'要確認';
    return value||'要確認';
  }

  function jobDetails(job){
    const review=job?.llm_review||{};
    const original=String(job?.title||'').trim();
    const snippet=String(job?.snippet||'').trim().slice(0,900);
    return `<details class="uxDetails"><summary>詳しく見る</summary>
      <div class="uxDetailGrid">
        <div><span>人の対応</span><b>${esc(detailStatus(review.human_dependency,'human'))}</b></div>
        <div><span>リアルタイム対応</span><b>${esc(detailStatus(review.synchronous_human_interaction,'sync'))}</b></div>
        <div><span>掲載確認</span><b>${isLiveATSVerified(job)?'確認済み':'要確認'}</b></div>
        <div><span>AI利用</span><b>${job?.ai_tool_policy_status==='explicitly-allowed'?'利用可の記載あり':'応募前に確認'}</b></div>
      </div>
      ${original?`<div class="uxOriginal"><b>元の求人名</b><p>${esc(original)}</p></div>`:''}
      ${snippet?`<details class="uxOriginalText"><summary>求人原文を見る（英語の場合あり）</summary><p>${esc(snippet)}</p></details>`:''}
    </details>`;
  }

  function actionButtons(job,{compact=false}={}){
    const id=String(job?.id||'');
    const favorite=state.favorite.has(id),applied=state.applied.has(id),declined=state.declined.has(id);
    const cls=compact?' uxTinyActions':'';
    return `<div class="uxActions${cls}">
      <button class="btn ghost favorite" data-id="${esc(id)}">${favorite?'★ 保存済み':'☆ 保存'}</button>
      <button class="btn ghost applied" data-id="${esc(id)}">${applied?'↩ 応募済み解除':'✓ 応募済み'}</button>
      <button class="btn ghost decline" data-id="${esc(id)}">${declined?'↩ 戻す':'× 除外'}</button>
    </div>`;
  }

  function destinationButtons(job,{compact=false}={}){
    const indeed=indeedDestination(job),official=officialUrl(job);
    return `<div class="uxDestinations${compact?' compact':''}">
      <a class="btn primary uxIndeed" href="${esc(indeed.url)}" target="_blank" rel="noopener noreferrer">${esc(indeed.label)} →</a>
      ${official?`<a class="btn ghost uxOfficial" href="${esc(official)}" target="_blank" rel="noopener noreferrer">公式求人</a>`:''}
    </div>${!indeed.exact?'<div class="uxIndeedNote">※ Indeedの個別掲載URLを確認できていないため、会社名＋求人名の検索結果を開きます。</div>':''}`;
  }

  function groupRows(rows){
    if(state.mode!=='all')return rows.map(job=>({key:String(job.id),jobs:[job],primary:job,info:familyInfo(job)}));
    const groups=new Map();
    for(const job of rows){
      const key=jobFamily(job);
      if(!groups.has(key))groups.set(key,{key,jobs:[],primary:job,info:FAMILY[key]||FAMILY.other});
      groups.get(key).jobs.push(job);
    }
    return [...groups.values()];
  }

  function compactAlternative(job){
    const indeed=indeedDestination(job),official=officialUrl(job);
    return `<div class="uxAlt">
      <div class="uxAltMain"><b>${esc(titleJa(job))}</b><span>${esc(job.company||'会社名不明')} · ${esc(locationJa(job))}</span></div>
      <div class="uxAltLinks"><a href="${esc(indeed.url)}" target="_blank" rel="noopener noreferrer">Indeed</a>${official?`<a href="${esc(official)}" target="_blank" rel="noopener noreferrer">公式</a>`:''}</div>
      ${actionButtons(job,{compact:true})}
    </div>`;
  }

  function groupCard(group){
    const job=group.primary,info=group.info,alternatives=group.jobs.slice(1);
    const isNew=isNewCandidate(job);
    return `<article class="card uxCard" data-family="${esc(group.key)}">
      <div class="uxTopline"><span class="uxType">${esc(info.label)}</span><span class="fresh">${esc(ageLabel(freshnessReference(job)))}</span></div>
      <h3>${esc(titleJa(job))}</h3>
      <div class="uxCompany">${esc(job.company||'会社名不明')} <span>·</span> ${esc(locationJa(job))}${isNew?' <em>NEW</em>':''}</div>
      <p class="uxSummary">${esc(info.summary)}</p>
      <div class="uxTags">${statusTags(job).map(tag=>`<span>${esc(tag)}</span>`).join('')}</div>
      ${job.ai_tool_use_permission_confirm_required===true?'<div class="uxCaution">AIで補助できそうな仕事ですが、外部AIの利用許可は求人票だけでは確認できません。応募後・業務開始前に確認してください。</div>':''}
      ${destinationButtons(job)}
      ${actionButtons(job)}
      ${jobDetails(job)}
      ${alternatives.length?`<details class="uxSimilar"><summary>似た求人があと${alternatives.length}件あります</summary><div class="uxAltList">${alternatives.map(compactAlternative).join('')}</div></details>`:''}
    </article>`;
  }

  function bindActions(){
    document.querySelectorAll('#jobs .favorite').forEach(button=>button.onclick=()=>{
      const id=String(button.dataset.id||'');
      if(state.favorite.has(id))state.favorite.delete(id);else state.favorite.add(id);
      persistSet('savedJobs',state.favorite);render();
    });
    document.querySelectorAll('#jobs .applied').forEach(button=>button.onclick=()=>{
      const id=String(button.dataset.id||'');
      if(state.applied.has(id)){state.applied.delete(id);delete state.appliedAt[id]}
      else{state.applied.add(id);state.declined.delete(id);state.appliedAt[id]=`${localDateKey()}T${new Date().toTimeString().slice(0,8)}`}
      persistSet('appliedJobs',state.applied);persistSet('declinedJobs',state.declined);persistMap('appliedAt',state.appliedAt);render();
    });
    document.querySelectorAll('#jobs .decline').forEach(button=>button.onclick=()=>{
      const id=String(button.dataset.id||'');
      if(state.declined.has(id))state.declined.delete(id);
      else{state.declined.add(id);state.favorite.delete(id);state.applied.delete(id);delete state.appliedAt[id]}
      persistSet('declinedJobs',state.declined);persistSet('savedJobs',state.favorite);persistSet('appliedJobs',state.applied);persistMap('appliedAt',state.appliedAt);render();
    });
  }

  function renderUX(){
    let rows=currentRows();
    if(category!=='all')rows=rows.filter(job=>familyInfo(job).category===category);
    const groups=groupRows(rows);
    const jobs=document.querySelector('#jobs');
    if(!jobs)return;
    const names={all:'今日見る候補',favorite:'保存した求人',applied:'応募済み',declined:'除外済み',high:'おすすめ',dual:'おすすめ',review:'候補'};
    $('#listTitle').textContent=names[state.mode]||'求人候補';
    $('#resultCount').textContent=state.mode==='all'?`${groups.length}種類 / ${rows.length}件`:`${rows.length}件`;
    if(!rows.length){
      jobs.innerHTML='<div class="empty"><b>この条件では候補がありません。</b><br>分類を「すべて」に戻すか、検索条件を変えてください。</div>';
      syncHealth();
      return;
    }
    jobs.innerHTML=groups.map(groupCard).join('');
    bindActions();
    syncHealth();
  }

  function syncHealth(){
    const source=document.querySelector('#sourceHealth');
    const body=document.querySelector('#uxHealthBody');
    if(source&&body)body.textContent=source.textContent;
  }

  function installStyles(){
    const style=document.createElement('style');
    style.textContent=`
      .uxHidden{display:none!important}.stats{grid-template-columns:repeat(3,1fr)!important}.uxCategoryBar{display:flex;gap:7px;overflow:auto;padding-top:10px;scrollbar-width:none}.uxCategory{white-space:nowrap;border:1px solid var(--line);background:#0b1d2e;color:#9fb5c8;border-radius:999px;padding:9px 12px;font-size:11px;cursor:pointer}.uxCategory.active{background:#dff8ff;color:#07111f;border-color:#dff8ff;font-weight:900}.uxHealth{margin-top:10px;font-size:10px;color:var(--muted)}.uxHealth summary{cursor:pointer;color:#91a9bd}.uxHealth div{padding:8px 0 0;line-height:1.6}.uxCard{padding:16px;border-color:#23415b;box-shadow:0 9px 22px #0002}.uxTopline{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}.uxType{font-size:10px;font-weight:900;background:#183449;color:#bfeeff;padding:5px 8px;border-radius:999px}.uxCard h3{font-size:17px;line-height:1.45;margin:0 0 5px}.uxCompany{font-size:11px;color:#a8c2d8}.uxCompany span{color:#59758c;margin:0 3px}.uxCompany em{font-style:normal;font-size:9px;background:#173527;color:#a6f0c5;padding:3px 5px;border-radius:999px;margin-left:5px}.uxSummary{font-size:12px;line-height:1.75;color:#c4d4e1;margin:12px 0 9px}.uxTags{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}.uxTags span{font-size:9px;background:#102b3c;color:#bfe0ef;padding:5px 7px;border-radius:999px}.uxCaution{font-size:10px;line-height:1.6;background:#2b2318;border:1px solid #4e3a22;color:#f7d9a6;border-radius:10px;padding:8px 9px;margin:8px 0}.uxDestinations{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:7px;margin-top:11px}.uxDestinations .uxIndeed{font-size:13px;padding:13px 12px}.uxDestinations .uxOfficial{display:grid;place-items:center;min-width:82px}.uxIndeedNote{font-size:9px;color:#718ba1;line-height:1.5;margin-top:5px}.uxActions{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:9px}.uxActions .btn{font-size:10px;padding:9px 6px}.uxDetails,.uxSimilar{margin-top:10px;border-top:1px solid #1b3449;padding-top:9px}.uxDetails>summary,.uxSimilar>summary{cursor:pointer;font-size:10px;color:#92adc2;list-style:none}.uxDetails>summary::-webkit-details-marker,.uxSimilar>summary::-webkit-details-marker{display:none}.uxDetailGrid{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;margin-top:9px}.uxDetailGrid>div{background:#071522;border:1px solid var(--line);border-radius:10px;padding:8px}.uxDetailGrid span{display:block;color:#7f99ae;font-size:8px}.uxDetailGrid b{font-size:10px;color:#dbe9f4}.uxOriginal{margin-top:9px;font-size:10px}.uxOriginal b{color:#9fb4c5}.uxOriginal p{margin:4px 0;color:#c1d0dc;line-height:1.5}.uxOriginalText{font-size:9px;color:#7790a5;margin-top:8px}.uxOriginalText summary{cursor:pointer}.uxOriginalText p{line-height:1.65;color:#8fa5b7}.uxAltList{display:grid;gap:7px;margin-top:9px}.uxAlt{background:#071522;border:1px solid #1c374d;border-radius:12px;padding:10px}.uxAltMain b{display:block;font-size:11px;line-height:1.4}.uxAltMain span{display:block;font-size:9px;color:#829bb0;margin-top:3px}.uxAltLinks{display:flex;gap:12px;margin-top:7px}.uxAltLinks a{font-size:10px;color:#78dff2;text-decoration:none;font-weight:800}.uxTinyActions{margin-top:7px}.uxTinyActions .btn{padding:7px 5px;font-size:9px}.note{margin-top:12px}.footer{margin-bottom:5px}
      @media(max-width:500px){.uxDestinations{grid-template-columns:1fr}.uxDestinations .uxOfficial{min-height:38px}.uxActions{grid-template-columns:repeat(3,1fr)}.uxCard h3{font-size:16px}.stats{grid-template-columns:repeat(3,1fr)!important}.stat{padding:8px 6px}.stat b{font-size:15px}}
    `;
    document.head.appendChild(style);
  }

  function setupShell(){
    document.documentElement.lang='ja';
    document.title='AI在宅求人ナビ';
    const title=document.querySelector('.title h1');if(title)title.textContent='AI在宅求人ナビ';
    const subtitle=document.querySelector('.title p');if(subtitle)subtitle.textContent='日本から応募できる、AIで補助しやすい完全在宅求人';
    const heroStrong=document.querySelector('.hero strong');if(heroStrong)heroStrong.textContent='今日見るべき求人だけ、分かりやすく';
    const heroP=document.querySelector('.hero p');if(heroP)heroP.textContent='似た仕事内容はひとつにまとめました。英語の原文や細かな判定は「詳しく見る」に収納。まずは仕事内容と応募先だけ見ればOKです。';
    const stats=[...document.querySelectorAll('.stat')];
    if(stats[0]?.querySelector('span'))stats[0].querySelector('span').textContent='現在の候補';
    if(stats[1])stats[1].classList.add('uxHidden');
    if(stats[2]?.querySelector('span'))stats[2].querySelector('span').textContent='今日の応募';
    if(stats[3]?.querySelector('span'))stats[3].querySelector('span').textContent='最終更新';
    const openIndeed=document.querySelector('#openIndeed');if(openIndeed)openIndeed.textContent='Indeedで求人を探す';
    const source=document.querySelector('#sourceHealth');if(source)source.classList.add('uxHidden');
    if(source&&!document.querySelector('#uxHealth')){
      const health=document.createElement('details');health.id='uxHealth';health.className='uxHealth';health.innerHTML='<summary>更新状況・判定基準を見る</summary><div id="uxHealthBody"></div>';
      source.insertAdjacentElement('afterend',health);
    }
    document.querySelectorAll('#chips .chip').forEach(chip=>{
      const mode=chip.dataset.mode;
      if(['high','dual','review'].includes(mode))chip.classList.add('uxHidden');
      if(mode==='all')chip.textContent='おすすめ';
      if(mode==='favorite')chip.textContent='★ 保存';
      if(mode==='applied')chip.textContent='✓ 応募済み';
      if(mode==='declined')chip.textContent='× 除外済み';
    });
    const chips=document.querySelector('#chips');
    if(chips&&!document.querySelector('#uxCategoryBar')){
      const bar=document.createElement('div');bar.id='uxCategoryBar';bar.className='uxCategoryBar';
      bar.innerHTML='<button class="uxCategory active" data-category="all">すべて</button><button class="uxCategory" data-category="evaluation">AI評価</button><button class="uxCategory" data-category="language">文章・翻訳</button><button class="uxCategory" data-category="data">データ作業</button><button class="uxCategory" data-category="technical">技術・専門</button>';
      chips.insertAdjacentElement('afterend',bar);
      bar.addEventListener('click',event=>{
        const button=event.target.closest?.('.uxCategory');if(!button)return;
        category=button.dataset.category||'all';
        bar.querySelectorAll('.uxCategory').forEach(x=>x.classList.toggle('active',x===button));
        render();
      });
    }
    const sort=document.querySelector('#sort');
    if(sort){sort.innerHTML='<option value="best">おすすめ順</option><option value="fresh">新しい順</option>';sort.value=['best','fresh'].includes(state.sort)?state.sort:'best';}
    const subrow=document.querySelector('.subrow small');if(subrow)subrow.textContent='保存・応募済み・除外はこの端末に記録されます。同じ種類の求人はまとめて表示します。';
    const note=document.querySelector('.note');if(note)note.innerHTML='<b>AI利用について：</b>「AI利用は要確認」は、求人票に外部AIの利用許可が明記されていないという意味です。技術的に自動化しやすくても、守秘義務や利用ルールは応募後・業務開始前に確認してください。';
    const footer=document.querySelector('.footer');if(footer)footer.textContent='AI在宅求人ナビ — 日本から応募できる完全在宅候補を厳選';
  }

  installStyles();
  setupShell();

  const previousRender=render;
  render=function(){
    previousRender();
    renderUX();
  };

  // app.js may already have completed its first asynchronous feed load by the
  // time this final Pages layer executes. Re-render once so the simplified UX
  // is deterministic in both fast-cache and slow-network cases.
  if(Array.isArray(state.jobs)&&state.jobs.length)render();

  window.__simplifiedJobUX={version:UX_VERSION,jobFamily,titleJa,indeedDestination,groupRows};
})();
