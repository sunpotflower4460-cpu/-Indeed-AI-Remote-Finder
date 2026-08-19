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
- Quality rows are stamped with `quality_policy_version=2` and `quality_gate=async-ai-remote-v2`. Older rows cannot re-enter the reserve pool until a fresh scan evaluates them under v2.
- Rows that survive the final presence gate are additionally stamped with `presence_gate_version=1` and `continuous_presence_risk=low`.
- The provider Work From Home classification is never used as proof of full remote. Discovery may use broad remote wording, but publication requires the listing text itself to pass the full-remote gate.

## LLM second opinion

- Deterministic filtering remains authoritative and works even when OpenAI is unavailable.
- The primary LLM pass reviews HIGH candidates first.
- Any unused portion of the same eight-attempt per-run budget can review v2 REVIEW candidates. This does not increase the per-run cap.
- When an available LLM review clearly confirms a mismatch — reject verdict, physical presence, frequent/confirmed occasional synchronous interaction, medium/high human dependency, or another high-confidence material blocker — the candidate is removed before final feed validation.
- An LLM-reviewed candidate with confidence >=80 and estimated end-to-end `automatable_fraction < 75` is too weak for this feed and is vetoed.
- LLM blockers explicitly describing human attendance, webcam/camera requirements, presence monitoring, desk-side waiting, attendance checks, or equivalent human-presence constraints are vetoed even if the nominal automation percentage is high.
- Missing LLM coverage never removes a deterministic candidate.
- Up to 2,400 characters of listing text are retained for the LLM audit so decisions are not based on a 640-character excerpt alone.

## Quantity and API budget policy

The user-facing goal is to keep at least 100 unapplied recommendations available. The server-side rolling pool may retain up to 150 quality-gated candidates so applications and declines do not immediately push the user's remaining stock below 100. The governing rule is: **quantity never overrides the quality gates above.** The 150 limit is surplus inventory, never a permission to pad the pool with weaker work.

Discovery uses broad task-focused anchor searches interleaved with many narrower rotating task profiles. This improves the chance of finding Indeed-backed candidates every day without turning the feed into a generic remote-job list. Only rows that pass the same publication gates enter the rolling pool.

The deep-search cadence is seven SerpApi requests per daily run. Seven requests × 31 days = 217, which fits inside the repository's 220-request monthly safety cap and avoids exhausting search budget early in the month. Quality-gated candidates may remain as reserve candidates for up to 30 days, while fresh/live candidates rank ahead of reserves.

## Client cache policy

The PWA uses `candidateCacheV3`. Quality-policy v2 already rejects pre-v2 candidates locally. When presence gate v1 is deployed, `index.html` performs a one-time purge of the existing `candidateCacheV3` before `app.js` loads, so pre-presence local reserve rows do not silently survive the rollout. The cache is then rebuilt only from the post-gate server feed and newly retained candidates.

## Safety boundary

Technical AI substitutability does not imply that an employer permits generative AI use or that confidential/personal information may be sent to external AI services. Those employment and data-handling rules still require confirmation before automation is used in real work.