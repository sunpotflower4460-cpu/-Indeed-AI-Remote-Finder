#!/usr/bin/env python3
"""Refresh AI-automatable remote-work candidates without crawling Indeed pages.

Live acquisition uses SerpApi's Google Jobs API. A job is accepted only when
Google Jobs returns an explicit Indeed entry in apply_options. The final link is
canonicalized to jp.indeed.com/viewjob?jk=... .

Required for scheduled live refresh: GitHub Actions secret SERPAPI_KEY.
When the secret is absent, the last known-good feed is preserved.
"""
from __future__ import annotations

import html, json, os, re, sys, urllib.parse, urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "jobs.json"
NOW = datetime.now(timezone.utc)

# 2 searches x 3 runs/day = <=186 searches in a 31-day month.
QUERIES = [
    ("structured", '完全在宅 フルリモート (データ入力 OR 商品登録 OR データ整理 OR 転記 OR スプレッドシート OR 集計 OR タグ付け)'),
    ("ai_language", '完全在宅 フルリモート (アノテーション OR AIトレーナー OR AI評価 OR 文字起こし OR 校正 OR 翻訳 OR リサーチ)'),
]
REMOTE_STRONG = {"完全在宅":74,"フルリモート":74,"完全リモート":74,"100%リモート":74,"fully remote":74,"100% remote":74,"全国どこからでも":68,"勤務地自由":60}
REMOTE_MEDIUM = {"在宅勤務":28,"在宅ワーク":28,"リモートワーク":28,"在宅":22,"remote":22,"work from home":28,"anywhere":24}
REMOTE_NEG = {"一部在宅":-35,"週1出社":-55,"週2出社":-60,"週3出社":-65,"出社あり":-65,"出社":-55,"常駐":-75,"出勤":-45,"ハイブリッド":-40,"hybrid":-40,"対面":-55,"訪問":-65}
NEGATED = ["出社不要","出社なし","出社はありません","出社一切なし","出社の必要なし","通勤不要","出勤不要","常駐なし","常駐不要","電話なし","電話対応なし","電話対応不要","架電なし","テレアポなし","対面なし","対面不要","訪問なし","訪問不要","接客なし","接客不要"]
AUTO_STRONG = {"アノテーション":34,"annotation":34,"labeling":32,"タグ付け":30,"データ入力":30,"data entry":30,"転記":30,"入力業務":28,"文字起こし":32,"transcription":32,"aiトレーナー":28,"ai trainer":28,"ai評価":30,"データ評価":28,"rater":28,"分類":26,"要約":28,"校正":27,"proofreading":27,"商品登録":27,"データ整理":27,"データ収集":24,"データチェック":27,"品質チェック":24,"品質評価":24,"リスト作成":25,"定型":22,"商品説明文":24,"カテゴリー設定":24,"在庫情報の更新":24}
AUTO_MEDIUM = {"リサーチ":18,"research":18,"情報収集":18,"ファクトチェック":16,"翻訳":18,"translation":18,"ライティング":15,"記事作成":14,"メール":12,"チャット":10,"事務":10,"excel":14,"スプレッドシート":14,"spreadsheet":14,"集計":16,"csv":14,"shopify":16,"ec運用":12,"モデレーション":18,"moderation":18,"コンテンツレビュー":16,"content review":16,"qa":12,"画像編集":10,"画像加工":10,"seo":8}
HARD_RISK = {"テレアポ","電話営業","新規営業","法人営業","個人営業","接客","訪問","出社","常駐","対面","運転","介護","看護","保育","調理","倉庫","配送","工事","警備","清掃","店舗","店頭","現場作業","施工","ドライバー","配達","販売スタッフ","梱包","撮影業務","商品撮影"}
SOFT_RISK = {"電話対応":18,"電話":10,"顧客折衝":22,"商談":25,"営業":22,"カスタマーサポート":13,"カスタマーサクセス":16,"オンライン面談":8,"ミーティング":8,"会議":8,"講師":18,"コンサル":18,"マネジメント":20,"採用面接":24,"クリエイティブディレクション":18,"撮影":24,"指示出し":12,"ディレクター":16,"ディレクション":16}
TAG_RULES = [
    ("完全リモート",list(REMOTE_STRONG)),
    ("データ",["データ入力","data entry","データ整理","データ収集","転記","集計","csv"]),
    ("AI評価",["アノテーション","annotation","aiトレーナー","ai trainer","ai評価","データ評価","rater","分類","タグ付け","labeling"]),
    ("文章",["文字起こし","transcription","翻訳","translation","校正","proofreading","要約","ライティング"]),
    ("リサーチ",["リサーチ","research","情報収集","ファクトチェック"]),
    ("事務",["事務","メール","チャット","excel","スプレッドシート","spreadsheet"]),
    ("EC",["商品登録","shopify","ec運用","商品説明文"]),
]

@dataclass
class Scores:
    remote:int; automation:int; freshness:int; risk:int; overall:int; tier:str
    remote_reasons:list[str]; automation_reasons:list[str]; risk_reasons:list[str]

def clean(v):
    v=html.unescape(re.sub(r"<[^>]+>"," ",str(v or "")))
    return re.sub(r"\s+"," ",v).strip()

def clamp(v): return max(0,min(100,round(v)))

def risk_text(text):
    t=text.lower()
    for p in NEGATED: t=t.replace(p.lower()," ")
    return t

def parse_relative_posted_at(value, now=None):
    if not value: return None
    now=now or NOW; s=clean(value).lower()
    if s in {"新着","たった今","just posted","today"}: return now
    patterns=[
        (r"(\d+)\s*(?:分|minutes?)\s*前?",lambda n:timedelta(minutes=n)),
        (r"(\d+)\s*(?:時間|hours?|hrs?)\s*前?",lambda n:timedelta(hours=n)),
        (r"(\d+)\s*(?:日|days?)\s*(?:以上)?\s*前?",lambda n:timedelta(days=n)),
        (r"(\d+)\s*(?:週|weeks?)\s*前?",lambda n:timedelta(weeks=n)),
        (r"(\d+)\s*(?:か月|ヶ月|ヵ月|months?)\s*前?",lambda n:timedelta(days=30*n)),
        (r"(\d+)\+?\s*days?\s*ago",lambda n:timedelta(days=n)),
        (r"(\d+)\s*hours?\s*ago",lambda n:timedelta(hours=n)),
        (r"(\d+)\s*weeks?\s*ago",lambda n:timedelta(weeks=n)),
    ]
    for pat,delta in patterns:
        m=re.search(pat,s)
        if m:
            n=int(m.group(1))
            if ("以上" in s or "+" in s) and ("日" in s or "day" in s): n=max(n,31)
            return now-delta(n)
    return None

def freshness_score(published, previous):
    if published:
        age=max(0,(NOW-published).total_seconds()/86400)
        score=98 if age<=1 else 92 if age<=3 else 84 if age<=7 else 70 if age<=14 else 52 if age<=30 else 34 if age<=60 else 18
    else: score=40
    if previous:
        score+=min(10,int(previous.get("seen_count") or 1)*2)
        try:
            last=previous.get("last_seen")
            last=datetime.fromisoformat(last.replace("Z","+00:00")) if last else None
            if last and NOW-last<=timedelta(days=3): score+=5
        except Exception: pass
    return clamp(score)

def score_job(text,published,previous,*,remote_api_filter=False):
    t=text.lower(); rt=risk_text(text); rr=[]; ar=[]
    remote=10
    if remote_api_filter: remote+=58; rr.append("Google Jobs:在宅勤務フィルタ")
    for k,p in REMOTE_STRONG.items():
        if k.lower() in t: remote+=p; rr.append(k)
    for k,p in REMOTE_MEDIUM.items():
        if k.lower() in t: remote+=p; rr.append(k)
    for k,p in REMOTE_NEG.items():
        if k.lower() in rt: remote+=p; rr.append("注意:"+k)
    if not rr: remote-=25
    remote=clamp(remote)
    automation=12; strong_hits=0
    for k,p in AUTO_STRONG.items():
        if k.lower() in t: automation+=p; strong_hits+=1; ar.append(k)
    for k,p in AUTO_MEDIUM.items():
        if k.lower() in t: automation+=p; ar.append(k)
    if strong_hits>=2: automation+=12
    elif strong_hits==0: automation-=18
    automation=clamp(automation)
    risks=[k for k in HARD_RISK if k.lower() in rt]
    soft=[(k,p) for k,p in SOFT_RISK.items() if k.lower() in rt]
    risk=clamp(sum(p for _,p in soft)+(70 if risks else 0)); risks += [k for k,_ in soft]
    fresh=freshness_score(published,previous)
    overall=clamp(.40*automation+.32*remote+.18*fresh+10-.42*risk)
    hard=any(k.lower() in rt for k in HARD_RISK)
    if hard: overall=min(overall,54)
    explicit=any(k.lower() in t for k in REMOTE_STRONG)
    high_fresh=published is not None and NOW-published<=timedelta(days=14)
    review_fresh=published is None or NOW-published<=timedelta(days=30)
    if automation>=82 and remote>=82 and high_fresh and risk<=8 and not hard and strong_hits>=2 and explicit: tier="high"
    elif automation>=64 and remote>=62 and risk<=35 and not hard and review_fresh: tier="review"
    else: tier="hidden"
    return Scores(remote,automation,fresh,risk,overall,tier,rr[:6],ar[:8],risks[:6])

def tags_for(text):
    t=text.lower(); tags=[label for label,keys in TAG_RULES if any(k.lower() in t for k in keys)]
    return tags[:5] or ["要確認"]

def previous_jobs():
    try:
        d=json.loads(OUT.read_text(encoding="utf-8")); return {r["id"]:r for r in d.get("jobs",[]) if r.get("id")}
    except Exception: return {}

def canonical_indeed_url(link):
    try:
        p=urllib.parse.urlparse(link); host=p.netloc.lower().split(":")[0]
        if not (host=="indeed.com" or host.endswith(".indeed.com")): return None
        q=urllib.parse.parse_qs(p.query); jid=(q.get("jk") or q.get("vjk") or [None])[0]
        if not jid: return None
        return f"https://jp.indeed.com/viewjob?jk={urllib.parse.quote(jid)}",jid
    except Exception: return None

def find_indeed_apply(job):
    for o in job.get("apply_options") or []:
        title=clean(o.get("title")); link=clean(o.get("link"))
        if "indeed" not in title.lower() and "indeed." not in link.lower(): continue
        found=canonical_indeed_url(link)
        if found: return found
    return None

def flatten_highlights(job):
    parts=[]
    for s in job.get("job_highlights") or []:
        parts.append(clean(s.get("title")))
        parts.extend(clean(x) for x in s.get("items") or [])
    return " ".join(x for x in parts if x)

def serpapi_fetch(query,api_key):
    params={"engine":"google_jobs","q":query,"location":"Japan","hl":"ja","gl":"jp","ltype":"1","api_key":api_key,"output":"json"}
    url="https://serpapi.com/search.json?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={"User-Agent":"AI-Remote-Finder/3.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=30) as r: return json.loads(r.read().decode("utf-8"))

def build_row(job,category,previous):
    indeed=find_indeed_apply(job)
    if not indeed: return None
    url,jid=indeed; title=clean(job.get("title")); company=clean(job.get("company_name")); location=clean(job.get("location")); desc=clean(job.get("description")); hi=flatten_highlights(job); ex=" ".join(clean(x) for x in job.get("extensions") or []); via=clean(job.get("via"))
    if not title: return None
    posted=clean((job.get("detected_extensions") or {}).get("posted_at")); published=parse_relative_posted_at(posted); old=previous.get(jid)
    text=" ".join([title,company,location,desc,hi,ex]); s=score_job(text,published,old,remote_api_filter=True)
    if s.tier=="hidden": return None
    snippet=desc or hi
    if len(snippet)>640: snippet=snippet[:637].rstrip()+"..."
    return {"id":jid,"title":title,"company":company,"location":location,"snippet":snippet,"url":url,"tier":s.tier,"score":s.overall,"automation_confidence":s.automation,"remote_confidence":s.remote,"freshness_confidence":s.freshness,"human_dependency_risk":s.risk,"automation_reasons":s.automation_reasons,"remote_reasons":s.remote_reasons,"risk_reasons":s.risk_reasons,"tags":tags_for(text),"category":category,"posted_label":posted or None,"search_published_at":published.isoformat() if published else None,"first_seen":old.get("first_seen") if old else NOW.isoformat(),"last_seen":NOW.isoformat(),"seen_count":int(old.get("seen_count") or 0)+1 if old else 1,"source":"Google Jobs via SerpApi; Indeed apply option verified","via":via}

def main():
    key=os.environ.get("SERPAPI_KEY","").strip()
    if not key:
        print("SERPAPI_KEY is not configured; preserving last known-good feed."); return
    previous=previous_jobs(); found={}; errors=[]; ok=raw=indeed_count=0
    for category,query in QUERIES:
        try:
            p=serpapi_fetch(query,key)
            if p.get("error"): raise RuntimeError(str(p["error"]))
            ok+=1; jobs=p.get("jobs_results") or []; raw+=len(jobs)
            for job in jobs:
                if find_indeed_apply(job): indeed_count+=1
                row=build_row(job,category,previous)
                if not row: continue
                cur=found.get(row["id"])
                if not cur or (row["tier"]=="high",row["score"])>(cur["tier"]=="high",cur["score"]): found[row["id"]]=row
        except Exception as e:
            errors.append(f"{category}: {e}"); print(f"WARN [{category}] {e}",file=sys.stderr)
    if ok==0:
        print("ERROR: provider unavailable; preserving previous feed",file=sys.stderr); raise SystemExit(2)
    jobs=sorted(found.values(),key=lambda r:(0 if r["tier"]=="high" else 1,-r["freshness_confidence"],-r["score"],-r["automation_confidence"]))[:80]
    payload={"generated_at":NOW.isoformat(),"query_success":ok,"query_total":len(QUERIES),"raw_jobs":raw,"indeed_apply_jobs":indeed_count,"errors":errors[:8],"method":"serpapi-google-jobs-indeed-apply-only","provider_configured":True,"jobs":jobs}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    high=sum(r["tier"]=="high" for r in jobs); review=sum(r["tier"]=="review" for r in jobs)
    print(f"wrote {len(jobs)} ({high} high/{review} review); queries {ok}/{len(QUERIES)}, raw {raw}, Indeed apply {indeed_count}")

if __name__=="__main__": main()
