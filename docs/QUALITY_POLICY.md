# AI Remote Finder quality contract — v2 + presence gate

Production recommendations are not a generic remote-job list. A published candidate must be suitable for an asynchronous AI-substitution workflow.

## Required

- Indeed individual application URL verified from structured Google Jobs data.
- The listing text itself provides explicit, unconditional full-remote evidence (for example 完全在宅 / フルリモート / 完全リモート / 100%リモート).
- Conditional or partial remote wording is rejected, including 在宅週1〜2日, 月1回出社, 一部在宅, 出社併用, 慣れたら在宅, 原則/基本/ほぼフルリモート, and フルリモート相談可.
- No core requirement for synchronous human attention such as calls, live customer support, meetings, negotiation, ongoing coordination, progress management, customer windows, or escalation handling.
- No explicit requirement for the **human worker** to remain continuously present or observable, such as camera/webcam always on, Zoom/Teams always connected for attendance, continuous screen sharing, PC/desk-side waiting, mandatory presence checks, inability to leave the desk, or random identity/attendance checks that require the person to respond.
- A fixed working schedule, an always-on software login/session, automated monitoring, or a fast machine-response SLA by itself is **not** a human-presence blocker. Software/RPA can technically remain online and respond unattended. Rejection requires evidence that the person themselves must remain present or be personally available.
- Explicit negations such as カメラ常時ON不要 / 在席確認なし / no webcam requirement are scrubbed before the presence test so they do not create false rejections.
- REVIEW candidates require `automation_confidence >= 64`, `human_dependency_risk <= 18`, and at least two distinct automation signals.
- Quality rows are stamped with `quality_policy_version=2` and `quality_gate=async-ai-remote-v2`.
- Rows that pass acquisition-time full-listing attendance screening are stamped with `full_listing_presence_screened=true`.
- Rows that survive the final presence gate are stamped with `presence_gate_version=1` and `continuous_presence_risk=low`.
- A missing job may re-enter the server reserve only if it still satisfies the current v2 quality contract **and** retains the full-listing and final presence-gate stamps above. A pre-presence v2 row cannot silently re-enter through carryover.
- The provider Work From Home classification is never used as proof of full remote. Discovery may use broad remote wording, but publication requires the listing text itself to pass the full-remote gate.

## LLM second opinion

- Deterministic filtering remains authoritative and works even when OpenAI is unavailable.
- The primary LLM pass reviews HIGH candidates first.
- Any unused portion of the same eight-attempt per-run budget can review v2 REVIEW candidates. This does not increase the per-run cap.
- A REVIEW row that receives a strict LLM pass remains deterministically `review`; the strict pass may be surfaced as an additional UI badge/filter only while the row still carries the current deterministic quality and presence proofs.
- When an available LLM review clearly confirms a mismatch — reject verdict, physical presence, frequent/confirmed occasional synchronous interaction, medium/high human dependency, or another high-confidence material blocker — the candidate is removed before final feed validation.
- An LLM-reviewed candidate with confidence >=80 and estimated end-to-end `automatable_fraction < 75` is too weak for this feed and is vetoed.
- LLM blockers explicitly describing human attendance, webcam/camera requirements, presence monitoring, desk-side waiting, attendance checks, or equivalent human-presence constraints are vetoed even if the nominal automation percentage is high.
- Missing LLM coverage never removes a deterministic candidate.
- Up to **6,000 characters** of listing text are retained for the LLM audit so decisions are not based on the short visual card excerpt alone.

## Quantity and API budget policy

The user-facing goal is to keep at least 100 unapplied recommendations available. The server-side rolling pool may retain up to 150 quality-gated candidates so applications and declines do not immediately push the user's remaining stock below 100. The governing rule is: **quantity never overrides the quality gates above.** The 150 limit is surplus inventory, never a permission to pad the pool with weaker work.

Discovery uses broad task-focused anchor searches interleaved with many narrower rotating task profiles. This improves the chance of finding Indeed-backed candidates every day without turning the feed into a generic remote-job list. Only rows that pass the same publication gates enter the rolling pool.

The nominal deep-search ceiling is seven SerpApi requests per run. Under the normal once-daily cadence, seven requests × 31 days = 217, which fits inside the repository's 220-request monthly safety cap. If extra manual or code-change refreshes push monthly usage ahead of that cadence, the acquisition layer spreads the remaining allowance across the remaining UTC calendar days and can lower the effective request count below seven. The pool-size request limit, remaining-month pacing, the hard monthly cap, and provider-reported headroom are cumulative ceilings: none of them may increase another limit or weaken publication quality. Quality-gated candidates may remain as reserve candidates for up to 30 days, while fresh/live candidates rank ahead of reserves.

## Client cache policy

The PWA uses `candidateCacheV4`. A cached row is accepted only when it still satisfies the current quality policy, current presence gate, freshness bounds, and client-side LLM veto rules. Server rows replace cached rows with the same ID.

The presence-gate rollout included a one-time purge of the older `candidateCacheV3` in `index.html` before `app.js` loads. New local reserve rows are therefore rebuilt only from candidates carrying the current server quality/presence evidence.

## Refresh/publication contract

Production refresh is performed from trusted `main`, not from pull-request code with production secrets. The daily schedule and explicit manual dispatch remain available. A relevant merged PR naturally creates a trusted `main` push, and that push is the **single automatic post-merge refresh path**; there is intentionally no second merged-PR dispatcher because production testing showed that the duplicate path spent SerpApi quota twice. Acquisition/provider failures preserve the last-known-good feed rather than writing an empty replacement as if it were fresh.

The final published JSON must pass both:

- `scripts/validate_feed.py`
- `scripts/validate_remote_feed.py`

The general validator allows at most 150 rows, matching the server reserve limit, and verifies that LLM metadata describes the rows that actually remain after final vetoes.

## Safety boundary

Technical AI substitutability does not imply that an employer permits generative AI use or that confidential/personal information may be sent to external AI services. It also does not establish that an employer permits the worker's duties to be delegated to unattended automation. Those employment and data-handling rules still require confirmation before automation is used in real work.