# AI Remote Finder quality contract — v2

Production recommendations are not a generic remote-job list. A published candidate must be suitable for an asynchronous AI-substitution workflow.

## Required

- Indeed individual application URL verified from structured Google Jobs data.
- The listing text itself provides explicit, unconditional full-remote evidence (for example 完全在宅 / フルリモート / 完全リモート / 100%リモート).
- Conditional or partial remote wording is rejected, including 在宅週1〜2日, 月1回出社, 一部在宅, 出社併用, 慣れたら在宅, 原則/基本/ほぼフルリモート, and フルリモート相談可.
- No core requirement for synchronous human attention such as calls, live customer support, meetings, real-time monitoring, negotiation, ongoing coordination, progress management, customer windows, or escalation handling.
- REVIEW candidates require `automation_confidence >= 64`, `human_dependency_risk <= 18`, and at least two distinct automation signals.
- Quality rows are stamped with `quality_policy_version=2` and `quality_gate=async-ai-remote-v2`. Older rows cannot re-enter the reserve pool until a fresh scan evaluates them under v2.
- The provider Work From Home classification is never used as proof of full remote. Discovery may use broad remote wording, but publication requires the listing text itself to pass the full-remote gate.

## LLM second opinion

- Deterministic filtering remains authoritative and works even when OpenAI is unavailable.
- The primary LLM pass reviews HIGH candidates first.
- Any unused portion of the same eight-attempt per-run budget can review v2 REVIEW candidates. This does not increase the per-run cap.
- When an available LLM review clearly confirms a mismatch — reject verdict, physical presence, frequent synchronous interaction, high human dependency, or another high-confidence material blocker — the candidate is removed before final feed validation.
- Missing LLM coverage never removes a deterministic candidate.
- Up to 2,400 characters of listing text are retained for the LLM audit so decisions are not based on a 640-character excerpt alone.

## Quantity and API budget policy

The server target remains 100 candidates, but quantity never overrides the quality gates above. Discovery breadth is increased through 72 rotating task-specific searches and rolling retention of already quality-gated candidates rather than by weakening the publication threshold.

The deep-search cadence is seven SerpApi requests per daily run. Seven requests × 31 days = 217, which fits inside the repository's 220-request monthly safety cap and avoids exhausting search budget early in the month. Quality-gated candidates may remain as reserve candidates for up to 30 days, while fresh/live candidates rank ahead of reserves.

## Client cache policy

The PWA uses `candidateCacheV3`. The cache generation changed with quality policy v2 so old v1 candidates are not silently resurfaced on iPhone. Cached rows are rechecked against v2 thresholds before they can appear as local reserve candidates.

## Safety boundary

Technical AI substitutability does not imply that an employer permits generative AI use or that confidential/personal information may be sent to external AI services. Those employment and data-handling rules still require confirmation before automation is used in real work.
